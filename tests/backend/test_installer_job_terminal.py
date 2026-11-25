"""A terminal job status is final: a job never reads ``failed`` and then ``completed``.

gos-as-a-service#106: with two realms requested a few seconds apart, one job read
``failed`` ("job in 'extensions', expected 'pending' or 'provisioning'") and
27 s later ``completed``. The cause was a second provision kick: the provision
heartbeat re-kicks a job that is waiting on its own 30 s stand re-check, so two
kick chains exist for one job. One moves the job to ``extensions``; the other
then raised from the status guard, the kick runner failed the job over it, and
the deploy task later wrote ``registering`` and ``completed`` over ``failed``.

These tests run the installer's real main.py on a simulated IC
(``installer_sim``), the only way to see the race: it needs timers, yielded
calls and a clock.
"""

import pytest

import installer_sim
from installer_sim import simulate

SAFE_PATH = ["provisioning", "extensions", "registering", "completed"]
TERMINAL_STATUSES = ("completed", "failed", "failed_verification", "cancelled")


@pytest.fixture(scope="module")
def installer():
    return installer_sim.load_installer()


@pytest.fixture(autouse=True)
def _empty_installer_db(installer):
    def wipe():
        for entity in (installer.DeploymentJob, installer.DeploymentJobRef, installer.DeployTask,
                       installer.DeployStep, installer.InstallerConfig):
            for row in list(entity.instances()):
                row.delete()

    wipe()
    yield
    wipe()


def statuses(sim, job_id):
    return [status for _time, status in sim.history[job_id]]


@pytest.mark.parametrize("heartbeat_phase_s", range(1, 140, 3))
def test_two_realms_provisioned_together_never_read_failed(installer, heartbeat_phase_s):
    """The heartbeat lands at every point of the stand wait and of the extension phase."""
    sim = simulate(installer, realms=2, heartbeat_phase_s=heartbeat_phase_s)

    assert len(sim.history) == 2
    for job_id in sim.history:
        assert statuses(sim, job_id) == SAFE_PATH
        assert sim.settlements[job_id] == ["succeeded"]
    assert sim.traps == []


def test_a_second_kick_on_a_job_in_extensions_is_a_no_op(installer):
    sim = simulate(installer, realms=1, heartbeat_phase_s=600, run_s=130)
    (job,) = installer.DeploymentJob.instances()
    assert job.status == "extensions"

    # What the stray kick chain does: run a pass on a job another pass took.
    with pytest.raises(installer.JobNotProvisioning):
        next(installer._provision_via_casals_gen(job.name))

    assert job.status == "extensions"
    assert sim.settlements == {}


def test_the_kick_runner_does_not_fail_a_job_that_moved_on(installer):
    sim = simulate(installer, realms=1, heartbeat_phase_s=600, run_s=130)
    (job,) = installer.DeploymentJob.instances()

    sim.at(sim.t + 1, lambda: sim.run(_kick(installer, job.name)))
    sim.run_until(sim.t + 2)  # the task is still running: registering starts at 134 s

    assert job.status == "extensions"
    assert sim.settlements == {}
    assert sim.traps == []


def _kick(installer, job_id):
    """The wrapper every timer and heartbeat kick runs through."""
    yield from installer.provision_kick_runner(
        job_id,
        run_gen=installer._provision_via_casals_gen,
        mark_failed=installer._mark_provision_failed,
        log_info=lambda message: None,
        log_error=lambda message: None,
    )


def test_a_late_deploy_task_does_not_reopen_a_failed_job(installer):
    """Registration is already running when something else fails the job: failed stays failed."""

    def fail_during_registration(sim):
        def operator_fails_the_job():
            (job,) = installer.DeploymentJob.instances()
            assert job.status == "registering"
            installer._fail_job(job, "failed by an operator")

        sim.at(135, operator_fails_the_job)  # registering from 134 s to 139 s

    sim = simulate(installer, realms=1, heartbeat_phase_s=600, setup=fail_during_registration)

    (job_id,) = sim.history
    assert statuses(sim, job_id) == ["provisioning", "extensions", "registering", "failed"]
    assert sim.settlements[job_id] == ["failed"]


@pytest.mark.parametrize("terminal", TERMINAL_STATUSES)
def test_no_writer_leaves_a_terminal_status(installer, terminal):
    simulate(installer, realms=0, run_s=0)
    job = installer.DeploymentJob(name="job_terminal", status=terminal, manifest_json="{}")

    for status in ("provisioning", "extensions", "registering", "completed", "failed"):
        assert installer._set_job_status(job, status) is False
        assert job.status == terminal


def test_retry_deployment_is_the_one_door_out_of_failed(installer):
    sim = simulate(installer, realms=0, run_s=0)
    job = installer.DeploymentJob(
        name="job_retry", status="failed", caller_principal=installer_sim.REGISTRY_ID, manifest_json="{}",
    )

    result = installer.retry_deployment(job.name)

    assert "Ok" in result
    assert job.status == "provisioning"
    assert sim.traps == []
