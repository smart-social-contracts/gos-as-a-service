"""Caller checks for the installer's job endpoints."""


def can_view_deployment_manifest(*, caller: str, owner: str, is_controller: bool) -> bool:
    if is_controller:
        return True
    return (owner or "") == (caller or "")


def can_enqueue_deployment(*, caller: str, registry_principal: str, is_controller: bool) -> bool:
    """Only the configured registry (which checked the invitation and held the credits) may file jobs."""
    if is_controller:
        return True
    return bool(registry_principal) and caller == registry_principal


def can_report_on_job(*, caller: str, casals_principal: str, is_controller: bool) -> bool:
    """Only Casals drives a job's progress; the job's owner must not name its own canisters."""
    if is_controller:
        return True
    return bool(casals_principal) and caller == casals_principal
