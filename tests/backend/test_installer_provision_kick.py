"""Tests for immediate Casals provision kick scheduling and in-progress lock."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from provision_kick import (
    HEARTBEAT_RETRY_STATUSES,
    PROVISION_ACTIVE_STALE_S,
    PROVISION_HEARTBEAT_INTERVAL_S,
    ProvisionAlreadyInProgress,
    claim_provision_lock,
    clear_provision_lock,
    provision_kick_runner,
    provision_lock_is_fresh,
    provisioning_job_ids_for_heartbeat,
    schedule_provision_kick,
    should_kick_provision_on_enqueue,
)


class _FakeJob:
    def __init__(self, name: str, status: str, provision_active_at: int = 0):
        self.name = name
        self.status = status
        self.provision_active_at = provision_active_at


def test_should_kick_when_casals_manifest_and_flag_enabled():
    assert should_kick_provision_on_enqueue(casals_manifest=True, provision_via_casals=True)
    assert not should_kick_provision_on_enqueue(casals_manifest=True, provision_via_casals=False)
    assert not should_kick_provision_on_enqueue(casals_manifest=False, provision_via_casals=True)


def test_schedule_provision_kick_uses_zero_delay_timer():
    timer_calls = []
    ran = []

    def fake_set_timer(duration, callback):
        timer_calls.append((duration, callback))

    def fake_runner(job_id: str):
        ran.append(job_id)
        if False:
            yield

    schedule_provision_kick(
        "job_test_1",
        set_timer=fake_set_timer,
        duration=lambda s: s,
        delay_s=0,
        runner=fake_runner,
    )

    assert len(timer_calls) == 1
    duration, callback = timer_calls[0]
    assert duration == 0
    list(callback())
    assert ran == ["job_test_1"]


def test_heartbeat_interval_is_ten_minutes():
    assert PROVISION_HEARTBEAT_INTERVAL_S == 600


def test_provisioning_job_ids_for_heartbeat_skips_fresh_lock():
    now = 1_700_000_000
    jobs = [
        _FakeJob("job_a", "provisioning", provision_active_at=now - 60),
        _FakeJob("job_b", "pending"),
        _FakeJob("job_d", "provisioning", provision_active_at=0),
        _FakeJob("job_e", "provisioning", provision_active_at=now - PROVISION_ACTIVE_STALE_S - 1),
    ]
    ids = provisioning_job_ids_for_heartbeat(
        jobs,
        terminal_statuses=("failed", "completed"),
        now_s=now,
    )
    assert ids == ["job_b", "job_d", "job_e"]


def test_heartbeat_never_reopens_a_failed_job():
    """A failed deploy is terminal.

    Re-kicking one replayed the whole bootstrap against a stand that already
    existed: `enter_setup` and `configure_canister_ids` failed on replay, and
    the failure that actually mattered (no ManagePermissions on the asset
    canister) sat behind "Retrying automatically". Recovery is an explicit
    retry_deployment, which resumes from the failed step.
    """
    now = 1_700_000_000
    jobs = [
        _FakeJob("job_failed", "failed", provision_active_at=0),
        _FakeJob("job_failed_verification", "failed_verification"),
        _FakeJob("job_cancelled", "cancelled"),
    ]
    ids = provisioning_job_ids_for_heartbeat(
        jobs,
        terminal_statuses=("failed", "failed_verification", "completed", "cancelled"),
        now_s=now,
    )
    assert ids == []


def test_heartbeat_retry_statuses_exclude_failed():
    assert "failed" not in HEARTBEAT_RETRY_STATUSES
    assert set(HEARTBEAT_RETRY_STATUSES) == {"pending", "provisioning"}


def test_claim_provision_lock_rejects_concurrent_pass():
    job = _FakeJob("job_x", "provisioning")
    now = 1_700_000_000
    claim_provision_lock(job, now_s=now)
    assert job.provision_active_at == now

    try:
        claim_provision_lock(job, now_s=now + 5)
        assert False, "expected ProvisionAlreadyInProgress"
    except ProvisionAlreadyInProgress:
        pass


def test_claim_provision_lock_allows_stale_lock_takeover():
    job = _FakeJob("job_x", "provisioning", provision_active_at=1_000)
    now = 1_000 + PROVISION_ACTIVE_STALE_S + 1
    claim_provision_lock(job, now_s=now)
    assert job.provision_active_at == now


def test_clear_provision_lock_resets_field():
    job = _FakeJob("job_x", "provisioning", provision_active_at=99)
    clear_provision_lock(job)
    assert job.provision_active_at == 0
    assert not provision_lock_is_fresh(job, now_s=100)


def test_provision_kick_runner_skips_benign_concurrent_pass():
    failed = []
    logs = []

    def _run_gen(job_id: str):
        raise ProvisionAlreadyInProgress("already running")
        if False:
            yield

    list(
        provision_kick_runner(
            "job_dup",
            run_gen=_run_gen,
            mark_failed=lambda jid, reason: failed.append((jid, reason)),
            log_info=lambda msg: logs.append(("info", msg)),
            log_error=lambda msg: logs.append(("error", msg)),
        )
    )

    assert failed == []
    assert any(level == "info" for level, _ in logs)


def test_provision_kick_runner_marks_real_failures():
    failed = []

    def _run_gen(job_id: str):
        raise RuntimeError("casals boom")
        if False:
            yield

    list(
        provision_kick_runner(
            "job_fail",
            run_gen=_run_gen,
            mark_failed=lambda jid, reason: failed.append((jid, reason)),
            log_info=lambda _msg: None,
            log_error=lambda _msg: None,
        )
    )

    assert failed == [("job_fail", "casals boom")]


def test_concurrent_pass_first_claims_second_benign():
    """Simulate two near-simultaneous kicks: second pass is benign while first holds lock."""
    job = _FakeJob("job_race", "provisioning")
    now = 2_000_000_000
    failed = []
    logs = []

    claim_provision_lock(job, now_s=now)

    def _second_pass(job_id: str):
        claim_provision_lock(job, now_s=now + 1)
        if False:
            yield

    list(
        provision_kick_runner(
            "job_race",
            run_gen=_second_pass,
            mark_failed=lambda jid, reason: failed.append((jid, reason)),
            log_info=lambda msg: logs.append(msg),
            log_error=lambda _msg: None,
        )
    )

    assert failed == []
    assert any("already in progress" in msg for msg in logs)
    assert job.provision_active_at == now

    clear_provision_lock(job)
    assert job.provision_active_at == 0


def test_lock_cleared_after_success_and_failure_paths():
    job = _FakeJob("job_clear", "provisioning")
    now = 3_000_000_000

    def _success(job_id: str):
        claim_provision_lock(job, now_s=now)
        try:
            yield
        finally:
            clear_provision_lock(job)

    def _failure(job_id: str):
        claim_provision_lock(job, now_s=now)
        try:
            raise RuntimeError("boom")
        finally:
            clear_provision_lock(job)

    list(
        provision_kick_runner(
            "job_clear",
            run_gen=_success,
            mark_failed=lambda *_a: None,
            log_info=lambda _m: None,
            log_error=lambda _m: None,
        )
    )
    assert job.provision_active_at == 0

    try:
        list(
            provision_kick_runner(
                "job_clear",
                run_gen=_failure,
                mark_failed=lambda *_a: None,
                log_info=lambda _m: None,
                log_error=lambda _m: None,
            )
        )
    except RuntimeError:
        pass
    assert job.provision_active_at == 0


def _installer_source() -> str:
    src_path = os.path.join(_REPO_ROOT, "src/realm_installer/main.py")
    with open(src_path, encoding="utf-8") as fh:
        return fh.read()


def test_provisioning_pass_does_not_reopen_a_failed_job():
    """Only pending/provisioning jobs are driven; a failed job needs an explicit retry."""
    src = _installer_source()
    gen = src.split("def _provision_via_casals_gen", 1)[1].split(
        "def _provision_via_casals_body", 1
    )[0]
    assert 'if status not in ("pending", "provisioning"):' in gen
    assert 'if status == "failed":' not in gen


def test_retry_keeps_error_and_resumes_instead_of_reprovisioning():
    """Retry must not wipe job.error — the portal shows it — and must resume."""
    src = _installer_source()
    retry = src.split("def retry_deployment", 1)[1].split("def provision_via_casals", 1)[0]
    assert 'job.error = ""' not in retry
    assert 'job.status = "provisioning"' in retry

    gen = src.split("def _provision_via_casals_gen", 1)[1].split(
        "def _provision_via_casals_body", 1
    )[0]
    assert "bootstrap_already_started" in gen
    assert "_resume_deploy_task" in gen


def test_deploy_task_id_is_not_minted_from_the_clock():
    """Wall-clock task ids collided across stands provisioned in the same round."""
    src = _installer_source()
    assert '"deploy_%d" % ic.time()' not in src
    start = src.split("def _start_extensions_for_job", 1)[1]
    assert "task_id = deploy_task_id(job.name)" in start
    assert "if _resume_deploy_task(job):" in start
