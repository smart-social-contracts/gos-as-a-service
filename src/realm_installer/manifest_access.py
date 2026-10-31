"""Caller checks for the installer's job endpoints."""


def can_view_deployment_manifest(*, caller: str, owner: str, is_controller: bool) -> bool:
    if is_controller:
        return True
    return (owner or "") == (caller or "")


def is_registry_or_controller(*, caller: str, registry_principal: str, is_controller: bool) -> bool:
    """Only the configured registry (which checked the invitation and held the credits) may file or cancel jobs."""
    if is_controller:
        return True
    return bool(registry_principal) and caller == registry_principal


def can_report_on_job(*, caller: str, casals_principal: str, is_controller: bool) -> bool:
    """Only Casals drives a job's progress; the job's owner must not name its own canisters."""
    if is_controller:
        return True
    return bool(casals_principal) and caller == casals_principal


def names_only_own_canisters(*, named_ids: dict, own_canister_ids: set) -> bool:
    """A manifest may name canisters only to upgrade a realm its requester deployed.

    Registration writes to the realm named by ``canister_ids.backend`` (name,
    frontend, slug), so a new deployment must never point at someone else's.
    """
    named = {(cid or "").strip() for cid in (named_ids or {}).values()}
    named.discard("")
    return named <= own_canister_ids
