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
    STALE_RUNNING_S,
    bootstrap_already_started,
    completed_step_kinds,
    deploy_task_id,
    describe_resume,
    enter_setup_already_satisfied,
    failed_bootstrap_step_kinds,
    plan_resume,
    steps_to_reset,
    task_belongs_to_job,
    task_has_progress,
)

NOW = 1_787_932_000


class _FakeStep:
    def __init__(self, idx, kind, status, started_at=0):
        self.idx = idx
        self.kind = kind
        self.status = status
        self.started_at = started_at


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


def test_grant_step_verifies_before_it_grants():
    grant = _installer_source().split("def _execute_grant_frontend_access", 1)[1].split(
        "def _finalize_task", 1
    )[0]
    assert "_frontend_commit_permitted" in grant
    assert "grant_frontend_access_outcome" in grant
