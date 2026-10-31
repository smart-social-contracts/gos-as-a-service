"""Pure helpers for Casals stand_create JSON arguments (no IC/basilisk imports)."""

import hashlib


def casals_placement_from_cfg(casals_cfg: dict) -> tuple[str, str]:
    subnet = (casals_cfg.get("subnet") or "").strip()
    subnet_type = (casals_cfg.get("subnet_type") or "").strip()
    return subnet, subnet_type


def new_job_id(*, timestamp: str, realm_name: str, requester: str) -> str:
    """``job_<timestamp>_<suffix>``; the suffix covers the requester, so two requesters never share an id.

    The stand name is derived from the id, so this also keeps their stands apart.
    """
    suffix = hashlib.sha256(f"{requester}|{realm_name}".encode()).hexdigest()[:4]
    return f"job_{timestamp}_{suffix}"


def stand_for_new_job(*, requested: str, realm_slug: str, job_id: str, enqueuer_is_controller: bool) -> str:
    """The stand a new job provisions into.

    Casals' ``stand_create`` hands back an existing stand whoever owns it, so a
    stand name taken from a user's manifest could land on another requester's
    canisters. Only a controller may name its stand; everyone else gets one that
    no other job can share.
    """
    requested = (requested or "").strip()
    if enqueuer_is_controller and requested:
        return requested
    return f"{realm_slug}-{job_id.split('_', 1)[-1].replace('_', '-')}"


def build_stand_create_args(
    section: str,
    stand: str,
    description: str,
    subnet: str = "",
    subnet_type: str = "",
) -> dict:
    args = {"section": section, "name": stand, "description": description}
    if subnet:
        args["subnet"] = subnet
    elif subnet_type:
        args["subnet"] = f"type:{subnet_type}"
    return args
