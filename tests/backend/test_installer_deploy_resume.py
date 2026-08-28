"""Tests for resuming a failed deploy instead of replaying the whole bootstrap.

Live failure this covers (job_20260828152332_870e, test.gos.earth): the first
pass created both canisters and completed ``enter_setup`` +
``configure_canister_ids``, then failed ``grant_frontend_access`` because the
installer holds no ManagePermissions on the asset canister. The heartbeat
re-kicked the job, a brand-new deploy task was minted with every step pending,
and all three bootstrap steps failed on replay — with the task id colliding
with another realm's task on top.
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from deploy_resume import (  # noqa: E402
    BOOTSTRAP_STEP_KINDS,
    EXTENSIONS_STALL_S,
    STALE_RUNNING_S,
    best_owned_task,
    bootstrap_already_started,
    completed_step_kinds,
    completed_step_signatures,
    deploy_task_id,
    describe_resume,
    enter_setup_already_satisfied,
    extensions_stall_reason,
    failed_bootstrap_step_kinds,
    plan_resume,
    steps_satisfied_by_prior_task,
    steps_to_reset,
    task_belongs_to_job,
    task_has_progress,
    task_owner_job,
)

NOW = 1_787_932_000


TEST8_BACKEND = "pxip5-cyaaa-aaaae-ag3dq-cai"
REALMTEST2_BACKEND = "xzc4e-4aaaa-aaaae-agzza-cai"
COLLIDED_TASK = "deploy_1787932135117151676"


class _FakeStep:
    def __init__(self, idx, kind, status, started_at=0, label=None):
        self.idx = idx
        self.kind = kind
        self.status = status
        self.started_at = started_at
        self.label = label if label is not None else kind


class _FakeTask:
    def __init__(self, name, target, status="queued", steps=None, started_at=0):
        self.name = name
        self.target_canister_id = target
        self.status = status
        self.steps = steps or []
        self.started_at = started_at


class _FakeJob:
    def __init__(self, name, backend, task_id="", created_at=0, status="extensions"):
        self.name = name
        self.backend_canister_id = backend
        self.ext_deploy_task_id = task_id
        self.created_at = created_at
        self.status = status


def _live_failure_steps():
    """The three bootstrap steps as job_20260828152332_870e left them."""
    return [
        _FakeStep(0, "enter_setup", "completed"),
        _FakeStep(1, "configure_canister_ids", "completed"),
        _FakeStep(2, "grant_frontend_access", "failed"),
    ]


# ── Task ids must be unique per job ────────────────────────────────────

def test_task_id_is_derived_from_the_job_id():
    assert deploy_task_id("job_20260828152332_870e") == "deploy_job_20260828152332_870e"


def test_task_ids_never_collide_across_jobs():
    """Two stands provisioned in the same IC round used to share one task id.

    IC time is identical for every message in a round, so "deploy_%d" % ic.time()
    minted the same name twice and the second job adopted the first realm's steps.
    """
    ids = {
        deploy_task_id("job_20260828152332_870e"),
        deploy_task_id("job_20260828152332_1a2b"),
        deploy_task_id("job_20260828152333_870e"),
    }
    assert len(ids) == 3


def test_task_id_stays_within_the_entity_field_limit():
    long_job = "job_" + "9" * 60
    task_id = deploy_task_id(long_job)
    assert len(task_id) <= 64
    assert task_id != deploy_task_id("job_" + "8" * 60)


def test_task_id_is_stable_so_a_second_pass_finds_the_same_task():
    assert deploy_task_id("job_x") == deploy_task_id("job_x")
    assert deploy_task_id("") == ""


# ── A completed enter_setup is never re-run ────────────────────────────

def test_completed_bootstrap_steps_are_not_reset():
    steps = _live_failure_steps()
    plan = plan_resume(steps, now_s=NOW)
    assert plan["resume"] is True
    assert plan["reset_idx"] == [2]
    assert plan["keep_completed"] == ["enter_setup", "configure_canister_ids"]
    assert "enter_setup" not in [steps[i].kind for i in plan["reset_idx"]]


def test_steps_to_reset_covers_failed_only():
    steps = _live_failure_steps() + [_FakeStep(3, "extension", "pending")]
    assert steps_to_reset(steps, now_s=NOW) == [2]


def test_running_step_is_left_alone_until_its_runner_is_provably_gone():
    steps = [_FakeStep(0, "enter_setup", "running", started_at=NOW - 60)]
    assert steps_to_reset(steps, now_s=NOW) == []

    stale = [_FakeStep(0, "enter_setup", "running", started_at=NOW - STALE_RUNNING_S - 1)]
    assert steps_to_reset(stale, now_s=NOW) == [0]


def test_resume_of_a_finished_task_resets_nothing():
    steps = [
        _FakeStep(0, "enter_setup", "completed"),
        _FakeStep(1, "configure_canister_ids", "completed"),
        _FakeStep(2, "grant_frontend_access", "completed"),
    ]
    plan = plan_resume(steps, now_s=NOW)
    assert plan["resume"] is True
    assert plan["reset_idx"] == []
    assert plan["has_progress"] is True


def test_no_task_steps_means_build_a_fresh_task():
    plan = plan_resume([], now_s=NOW)
    assert plan["resume"] is False
    assert task_has_progress([]) is False


def test_completed_step_kinds_are_reported_in_step_order():
    steps = list(reversed(_live_failure_steps()))
    assert completed_step_kinds(steps) == ["enter_setup", "configure_canister_ids"]


def test_describe_resume_names_what_is_skipped():
    summary = describe_resume(plan_resume(_live_failure_steps(), now_s=NOW))
    assert "enter_setup" in summary
    assert "2" in summary


# ── Provisioning is not re-driven when the canisters exist ─────────────

def test_existing_canisters_and_task_mean_resume_not_reprovision():
    assert bootstrap_already_started("pxip5-cyaaa-aaaae-ag3dq-cai", "deploy_job_x") is True


def test_a_job_that_never_got_canisters_still_provisions():
    assert bootstrap_already_started("", "deploy_job_x") is False
    assert bootstrap_already_started("pxip5-cyaaa-aaaae-ag3dq-cai", "") is False


def test_a_collided_task_from_another_realm_is_never_resumed():
    """A task id minted by the old clock scheme could belong to another realm."""
    ours = "pxip5-cyaaa-aaaae-ag3dq-cai"
    theirs = "icuo5-5aaaa-aaaac-bfrxa-cai"
    assert task_belongs_to_job(ours, ours) is True
    assert task_belongs_to_job(theirs, ours) is False
    assert task_belongs_to_job("", ours) is False


# ── A broken bootstrap is a failure, not a partial success ─────────────

def test_failed_grant_frontend_access_is_a_bootstrap_failure():
    assert failed_bootstrap_step_kinds(_live_failure_steps()) == ["grant_frontend_access"]


def test_a_failed_extension_is_not_a_bootstrap_failure():
    steps = [
        _FakeStep(0, "enter_setup", "completed"),
        _FakeStep(1, "extension", "failed"),
    ]
    assert failed_bootstrap_step_kinds(steps) == []


def test_bootstrap_kinds_cover_the_three_one_shot_steps():
    assert BOOTSTRAP_STEP_KINDS == (
        "enter_setup",
        "configure_canister_ids",
        "grant_frontend_access",
    )


# ── enter_setup idempotence (only when the step record was lost) ───────

def test_already_in_setup_rejection_counts_as_satisfied():
    assert enter_setup_already_satisfied("Realm already in setup") is True
    assert enter_setup_already_satisfied("realm already_in_setup") is True
    assert enter_setup_already_satisfied("founder already registered") is True


def test_other_enter_setup_rejections_stay_failures():
    assert enter_setup_already_satisfied("") is False
    assert enter_setup_already_satisfied("Rejection code 4, caller is not permitted") is False
    assert enter_setup_already_satisfied("Couldn't send message") is False


# ── One task name, two realms (the live collision) ────────────────────
#
# The installer DB on test.gos.earth holds two DeployTask rows both named
# deploy_1787932135117151676: one targeting pxip5 (RealmsTest8, left `queued`
# and unreachable because the name alias resolves to the later writer) and one
# targeting xzc4e (RealmTest2, `failed`). RealmTest2's 0/3 was served on
# RealmsTest8's card, and RealmsTest8's job sat in `extensions` for hours.

def _collided_rows():
    test8_own = _FakeTask(
        COLLIDED_TASK, TEST8_BACKEND, status="queued", started_at=100,
        steps=[
            _FakeStep(0, "enter_setup", "pending"),
            _FakeStep(1, "configure_canister_ids", "pending"),
            _FakeStep(2, "grant_frontend_access", "pending"),
        ],
    )
    test8_first_pass = _FakeTask(
        "deploy_1787931723064146992", TEST8_BACKEND, status="partial", started_at=50,
        steps=[
            _FakeStep(0, "enter_setup", "completed"),
            _FakeStep(1, "configure_canister_ids", "completed"),
            _FakeStep(2, "grant_frontend_access", "failed"),
        ],
    )
    realmtest2 = _FakeTask(
        COLLIDED_TASK, REALMTEST2_BACKEND, status="failed", started_at=110,
        steps=[
            _FakeStep(0, "enter_setup", "failed"),
            _FakeStep(1, "configure_canister_ids", "failed"),
            _FakeStep(2, "grant_frontend_access", "failed"),
        ],
    )
    return test8_own, test8_first_pass, realmtest2


def test_a_finished_task_settles_the_job_that_owns_it():
    _own, _first, realmtest2 = _collided_rows()
    test8_job = _FakeJob("job_20260828152332_870e", TEST8_BACKEND, COLLIDED_TASK, 200)
    realmtest2_job = _FakeJob("job_20260810100322_57c3", REALMTEST2_BACKEND, COLLIDED_TASK, 100)

    owner = task_owner_job(
        [test8_job, realmtest2_job], realmtest2.name, realmtest2.target_canister_id,
    )
    assert owner is realmtest2_job, "RealmTest2's failure must not land on the Test8 job"


def test_a_task_no_job_owns_touches_nothing():
    _own, _first, realmtest2 = _collided_rows()
    test8_job = _FakeJob("job_20260828152332_870e", TEST8_BACKEND, COLLIDED_TASK, 200)
    assert task_owner_job([test8_job], realmtest2.name, realmtest2.target_canister_id) is None


def test_a_realm_finds_its_own_task_among_the_collided_rows():
    own, first, realmtest2 = _collided_rows()
    picked = best_owned_task([own, first, realmtest2], TEST8_BACKEND)
    assert picked is first, "the row that got furthest for this realm wins"
    assert best_owned_task([own, first, realmtest2], REALMTEST2_BACKEND) is realmtest2
    assert best_owned_task([own, first, realmtest2], "") is None


def test_a_rebuild_carries_over_what_this_realm_already_completed():
    _own, first, _realmtest2 = _collided_rows()
    signatures = completed_step_signatures(first.steps)
    assert signatures == [
        ("enter_setup", "enter_setup"),
        ("configure_canister_ids", "configure_canister_ids"),
    ]

    rebuilt = [
        _FakeStep(0, "enter_setup", "pending"),
        _FakeStep(1, "configure_canister_ids", "pending"),
        _FakeStep(2, "grant_frontend_access", "pending"),
    ]
    assert steps_satisfied_by_prior_task(rebuilt, signatures) == [0, 1]


def test_carry_over_matches_extensions_by_label_not_just_kind():
    prior = [
        _FakeStep(0, "extension", "completed", label="ext-a"),
        _FakeStep(1, "extension", "failed", label="ext-b"),
    ]
    rebuilt = [
        _FakeStep(0, "extension", "pending", label="ext-a"),
        _FakeStep(1, "extension", "pending", label="ext-b"),
    ]
    assert steps_satisfied_by_prior_task(rebuilt, completed_step_signatures(prior)) == [0]


# ── Jobs stranded in `extensions` are reported, never re-driven ────────

def test_a_foreign_task_strands_the_job_and_says_so():
    _own, _first, realmtest2 = _collided_rows()
    reason = extensions_stall_reason(
        task=realmtest2,
        backend_canister_id=TEST8_BACKEND,
        recorded_task_id=COLLIDED_TASK,
        now_s=NOW + EXTENSIONS_STALL_S + 1,
        last_activity_s=NOW,
    )
    assert "belongs to another realm" in reason
    assert REALMTEST2_BACKEND in reason and TEST8_BACKEND in reason


def test_a_missing_task_strands_the_job():
    reason = extensions_stall_reason(
        task=None,
        backend_canister_id=TEST8_BACKEND,
        recorded_task_id=COLLIDED_TASK,
        now_s=NOW + EXTENSIONS_STALL_S + 1,
        last_activity_s=NOW,
    )
    assert "no longer exists" in reason


def test_a_task_that_finished_without_settling_the_job_strands_it():
    _own, first, _realmtest2 = _collided_rows()
    reason = extensions_stall_reason(
        task=first,
        backend_canister_id=TEST8_BACKEND,
        recorded_task_id=first.name,
        now_s=NOW + EXTENSIONS_STALL_S + 1,
        last_activity_s=NOW,
    )
    assert "finished as 'partial'" in reason


def test_a_job_whose_task_never_started_is_stranded():
    own, _first, _realmtest2 = _collided_rows()
    reason = extensions_stall_reason(
        task=own,
        backend_canister_id=TEST8_BACKEND,
        recorded_task_id=own.name,
        now_s=NOW + EXTENSIONS_STALL_S + 1,
        last_activity_s=NOW,
    )
    assert "never started" in reason


def test_a_recent_or_running_extensions_job_is_left_alone():
    own, _first, _realmtest2 = _collided_rows()
    assert extensions_stall_reason(
        task=own,
        backend_canister_id=TEST8_BACKEND,
        recorded_task_id=own.name,
        now_s=NOW + 60,
        last_activity_s=NOW,
    ) == ""

    running = _FakeTask(
        "deploy_job_x", TEST8_BACKEND, status="running",
        steps=[_FakeStep(0, "enter_setup", "running", started_at=NOW)],
    )
    assert extensions_stall_reason(
        task=running,
        backend_canister_id=TEST8_BACKEND,
        recorded_task_id=running.name,
        now_s=NOW + EXTENSIONS_STALL_S + 1,
        last_activity_s=NOW,
    ) == ""


# ── Wiring in the canister module (not importable without basilisk) ────

def _installer_source() -> str:
    src_path = os.path.join(_REPO_ROOT, "src/realm_installer/main.py")
    with open(src_path, encoding="utf-8") as fh:
        return fh.read()


def test_resume_refuses_a_task_that_targets_another_realm():
    resume = _installer_source().split("def _resume_deploy_task", 1)[1].split(
        "def _start_extensions_for_job", 1
    )[0]
    assert "task_belongs_to_job" in resume
    # Completed steps are only ever reset through the plan's reset list.
    assert 'step.status = "pending"' in resume
    assert "plan_resume" in resume


def test_a_broken_bootstrap_fails_the_job_instead_of_registering_it():
    check = _installer_source().split("def _check_job_after_extensions", 1)[1].split(
        "def _schedule_step_runner", 1
    )[0]
    assert "failed_bootstrap_step_kinds" in check
    assert "and not broken_bootstrap" in check
    # By owner, not by "first job that records this task id".
    assert "task_owner_job(" in check
    assert "for job in DeploymentJob.instances():" not in check


def test_the_status_query_never_serves_another_realms_steps():
    src = _installer_source()
    query = src.split("def get_deploy_task_status", 1)[1].split(
        "def get_deployment_manifest", 1
    )[0]
    assert "task_belongs_to_job" in query
    assert '"foreign"' in query
    # Operators paste the task id they see on the card; resolve it, don't
    # answer "unknown job_id" as if the record were gone.
    assert "DeployTask[job_id]" in query


def test_stranded_extension_jobs_are_reported_not_re_driven():
    src = _installer_source()
    reconcile = src.split("def _reconcile_stranded_extension_jobs", 1)[1].split(
        "def _arm_provision_heartbeat", 1
    )[0]
    assert "extensions_stall_reason" in reconcile
    assert "_mark_provision_failed" in reconcile
    assert "_schedule_provision_kick" not in reconcile
    assert "_resume_deploy_task" not in reconcile

    heartbeat = src.split("def _arm_provision_heartbeat", 1)[1].split(
        "def _provision_via_casals_gen", 1
    )[0]
    assert "_reconcile_stranded_extension_jobs()" in heartbeat


def test_a_rebuild_carries_prior_completed_steps_over():
    start = _installer_source().split("def _start_extensions_for_job", 1)[1]
    assert "_carry_over_completed_steps(job, task)" in start


def test_grant_step_verifies_before_it_grants():
    grant = _installer_source().split("def _execute_grant_frontend_access", 1)[1].split(
        "def _finalize_task", 1
    )[0]
    assert "_frontend_commit_permitted" in grant
    assert "grant_frontend_access_outcome" in grant
