"""The provision heartbeat costs what is in flight, not what has ever run.

Every 10 minutes the heartbeat used to load every DeployStep, DeployTask and
DeploymentJob the installer had ever stored (O(all rows) on a CPython
canister), whether or not any job needed attention, so an environment got
slowly more expensive for having been used. It now asks for the few jobs that
are pending, provisioning or in extensions through the job-status index.
"""

import pytest
from ic_python_db import Database
from ic_python_db import Entity

import installer_sim
from installer_sim import simulate

HISTORY_JOBS = 40
STEPS_PER_TASK = 5


class RowReads:
    """Counts the rows a block of code reads from the database: pages loaded and single loads."""

    def __enter__(self):
        self.rows = 0
        self._load_page, self._load = Database.load_page, Entity.load.__func__

        def load_page(db, *args, **kwargs):
            page = self._load_page(db, *args, **kwargs)
            self.rows += len(page)
            return page

        def load(cls, *args, **kwargs):
            self.rows += 1
            return self._load(cls, *args, **kwargs)

        Database.load_page, Entity.load = load_page, classmethod(load)
        return self

    def __exit__(self, *exc):
        Database.load_page, Entity.load = self._load_page, classmethod(self._load)


def finished_history(installer):
    """What an environment that has been used for a while holds: finished jobs with their tasks and steps."""
    for number in range(HISTORY_JOBS):
        job = installer._create_job(
            name=f"job_history_{number}", status="completed" if number % 3 else "failed", manifest_json="{}",
        )
        task = installer.DeployTask(name=f"deploy_{job.name}", status="completed", target_canister_id="x")
        job.ext_deploy_task_id = task.name
        for index in range(STEPS_PER_TASK):
            installer.DeployStep(task=task, idx=index, kind="setup_infrastructure", status="completed")


def one_tick(installer):
    """Run exactly one heartbeat tick, as the timer would, without the provision passes it arms.

    Returns the simulated IC and what the tick read from the database (the
    installer's configuration row and whatever the heartbeat asks for).
    """
    sim = simulate(installer, realms=0, heartbeat_phase_s=1, run_s=0, kick_passes=False)
    sim.observe = False
    installer._reindex_job_status()  # what init and post_upgrade do before the heartbeat is armed
    with RowReads() as reads:
        sim.run_until(2)
    return sim, reads


def test_an_idle_heartbeat_costs_the_same_whatever_has_run_before(installer):
    _sim, on_a_new_installer = one_tick(installer)
    finished_history(installer)

    _sim, after_a_history = one_tick(installer)

    # Only the configuration row, read a few times: none of the finished jobs, tasks or steps.
    assert after_a_history.rows == on_a_new_installer.rows
    assert after_a_history.rows <= 4


def test_the_heartbeat_reads_only_the_jobs_in_flight(installer):
    finished_history(installer)
    installer._create_job(name="job_waiting", status="provisioning", manifest_json="{}")

    sim, reads = one_tick(installer)

    assert reads.rows <= 4, f"read {reads.rows} rows for one job in flight"
    assert sim.provision_kicks == ["job_waiting"]


def test_a_stranded_extensions_job_is_still_failed_with_its_reason(installer):
    """The reconcile pass reads through the index too, and still finds a job nothing can advance."""
    finished_history(installer)
    job = installer._create_job(
        name="job_stranded", status="extensions", manifest_json="{}",
        created_at=1, completed_at=0, registry_canister_id=installer_sim.REGISTRY_ID,
    )

    simulate(installer, realms=0, heartbeat_phase_s=1, run_s=2)

    assert job.status == "failed"
    assert "no deploy task recorded" in job.error


def test_a_job_that_changes_status_moves_in_the_index(installer):
    job = installer._create_job(name="job_moving", status="pending", manifest_json="{}")
    assert [j.name for j in installer._jobs_with_status("pending")] == ["job_moving"]

    job.status = "extensions"

    assert installer._jobs_with_status("pending") == []
    assert [j.name for j in installer._jobs_with_status("extensions")] == ["job_moving"]

    job.delete()
    assert installer._jobs_with_status("extensions") == []


def test_jobs_stored_before_the_index_existed_are_indexed_at_upgrade(installer):
    job = installer._create_job(name="job_legacy", status="provisioning", manifest_json="{}")
    installer.DeploymentJob.db().field_index_remove(
        installer.DeploymentJob.get_full_type_name(), "status", "provisioning", job._id,
    )
    installer._job_status_index_ready = False
    assert installer.DeploymentJob.count_by("status", "provisioning") == 0

    assert installer._reindex_job_status()

    assert [j.name for j in installer._jobs_with_status("provisioning")] == ["job_legacy"]


def test_if_the_index_cannot_be_built_the_heartbeat_falls_back_to_the_full_scan(installer, monkeypatch):
    installer._create_job(name="job_unattended", status="pending", manifest_json="{}")
    installer._job_status_index_ready = False

    def broken(*args, **kwargs):
        raise RuntimeError("out of instructions")

    monkeypatch.setattr(installer.DeploymentJob, "rebuild_field_index", broken)

    assert [j.name for j in installer._jobs_with_status("pending")] == ["job_unattended"]
    assert installer._job_status_index_ready is False  # tried again at the next tick


def test_a_job_waiting_on_its_own_recheck_is_not_kicked_again(installer):
    """The heartbeat used to start a second re-check chain on a job that already had one."""
    now = 1_000
    waiting = installer._create_job(name="job_waiting", status="provisioning", manifest_json="{}")
    waiting.provision_recheck_at = now + 20
    overdue = installer._create_job(name="job_overdue", status="provisioning", manifest_json="{}")
    overdue.provision_recheck_at = now - 120  # its timer was lost, e.g. to an upgrade
    fresh = installer._create_job(name="job_fresh", status="pending", manifest_json="{}")

    ids = installer.provisioning_job_ids_for_heartbeat(
        [waiting, overdue, fresh], terminal_statuses=installer._JOB_TERMINAL_STATUSES, now_s=now,
    )

    assert sorted(ids) == ["job_fresh", "job_overdue"]


def test_a_job_created_with_the_default_status_is_indexed_too(installer):
    """A value equal to the property's default is not indexed by the constructor, so jobs are created through _create_job."""
    installer._job_status_index_ready = True  # as it is at runtime: the upgrade-time rebuild is done
    plain = installer.DeploymentJob(name="job_plain", status="pending", manifest_json="{}")
    assert installer.DeploymentJob.count_by("status", "pending") == 0  # the trap

    created = installer._create_job(name="job_created", status="pending", manifest_json="{}")

    assert [j.name for j in installer._jobs_with_status("pending")] == [created.name]
    assert plain.name not in [j.name for j in installer._jobs_with_status("pending")]
