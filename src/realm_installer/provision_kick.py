"""Immediate and heartbeat-driven kicks for Casals provisioning jobs."""

from __future__ import annotations

# Fallback retry interval when an enqueue-time kick fails or is missed (~10m observed in prod).
PROVISION_HEARTBEAT_INTERVAL_S = 600


def should_kick_provision_on_enqueue(*, casals_manifest: bool, provision_via_casals: bool) -> bool:
    """True when enqueue_deployment should schedule an immediate provision kick."""
    return bool(casals_manifest) and bool(provision_via_casals)


def provisioning_job_ids_for_heartbeat(jobs, *, terminal_statuses: tuple[str, ...]) -> list[str]:
    """Return job IDs in ``provisioning`` that the heartbeat should retry."""
    out: list[str] = []
    for job in jobs:
        status = (getattr(job, "status", None) or "pending")
        if status in terminal_statuses:
            continue
        if status != "provisioning":
            continue
        job_id = (getattr(job, "name", None) or "").strip()
        if job_id:
            out.append(job_id)
    return out


def schedule_provision_kick(job_id: str, *, set_timer, duration, delay_s: int, runner) -> None:
    """Arm a zero- or delayed timer that runs ``runner(job_id)`` (generator-safe)."""
    def _cb():
        yield from runner(job_id)

    set_timer(duration(int(delay_s)), _cb)
