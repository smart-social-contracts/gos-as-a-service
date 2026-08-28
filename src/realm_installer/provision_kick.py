"""Immediate and heartbeat-driven kicks for Casals provisioning jobs."""

from __future__ import annotations

# Fallback retry interval when an enqueue-time kick fails or is missed (~10m observed in prod).
PROVISION_HEARTBEAT_INTERVAL_S = 600

# Fresh in-progress lock — concurrent kicks within this window are benign skips.
PROVISION_ACTIVE_STALE_S = 30 * 60

# Statuses the heartbeat may re-drive. ``failed`` is deliberately absent: a
# failed job is terminal until someone acts on it. Re-kicking one re-ran the
# whole bootstrap from zero against a stand that was already created, so
# `enter_setup` and `configure_canister_ids` failed on replay and the real
# failure (e.g. a missing asset-canister permission) hid behind
# "Retrying automatically" forever.
HEARTBEAT_RETRY_STATUSES = ("pending", "provisioning")


class ProvisionAlreadyInProgress(Exception):
    """Raised when another provision pass already holds the job lock."""


def should_kick_provision_on_enqueue(*, casals_manifest: bool, provision_via_casals: bool) -> bool:
    """True when enqueue_deployment should schedule an immediate provision kick."""
    return bool(casals_manifest) and bool(provision_via_casals)


def _provision_active_at(job) -> int:
    return int(getattr(job, "provision_active_at", 0) or 0)


def provision_lock_is_fresh(job, *, now_s: int, stale_s: int = PROVISION_ACTIVE_STALE_S) -> bool:
    """True when ``provision_active_at`` indicates an active (non-stale) pass."""
    active_at = _provision_active_at(job)
    if active_at <= 0:
        return False
    return (now_s - active_at) < stale_s


def claim_provision_lock(job, *, now_s: int, stale_s: int = PROVISION_ACTIVE_STALE_S) -> None:
    """Atomically claim the in-progress lock (call before the first yield)."""
    active_at = _provision_active_at(job)
    if active_at > 0 and (now_s - active_at) < stale_s:
        raise ProvisionAlreadyInProgress(
            f"provision already in progress for job (since {active_at})"
        )
    job.provision_active_at = now_s


def clear_provision_lock(job) -> None:
    job.provision_active_at = 0


def provisioning_job_ids_for_heartbeat(
    jobs,
    *,
    terminal_statuses: tuple[str, ...],
    now_s: int,
    stale_s: int = PROVISION_ACTIVE_STALE_S,
) -> list[str]:
    """Return job IDs the heartbeat should re-drive (pending/provisioning only).

    Skips jobs with a fresh ``provision_active_at`` lock; includes jobs whose
    lock is stale so a crashed pass can be picked up again. Terminal jobs —
    ``failed`` included — are never re-driven here: recovery is an explicit
    ``retry_deployment``, which resumes from the failed step instead of
    replaying the whole bootstrap.
    """
    out: list[str] = []
    for job in jobs:
        status = (getattr(job, "status", None) or "pending")
        if status in terminal_statuses:
            continue
        if status not in HEARTBEAT_RETRY_STATUSES:
            continue
        if provision_lock_is_fresh(job, now_s=now_s, stale_s=stale_s):
            continue
        job_id = (getattr(job, "name", None) or "").strip()
        if job_id:
            out.append(job_id)
    return out


def provision_kick_runner(job_id: str, *, run_gen, mark_failed, log_info, log_error):
    """Timer/heartbeat wrapper: benign skip on concurrent pass, fail on real errors."""
    try:
        yield from run_gen(job_id)
    except ProvisionAlreadyInProgress as e:
        log_info(f"provision already in progress for {job_id}: {e}")
    except Exception as e:
        mark_failed(job_id, str(e))
        log_error(f"provision kick failed: {e}")


def schedule_provision_kick(job_id: str, *, set_timer, duration, delay_s: int, runner) -> None:
    """Arm a zero- or delayed timer that runs ``runner(job_id)`` (generator-safe)."""
    def _cb():
        yield from runner(job_id)

    set_timer(duration(int(delay_s)), _cb)
