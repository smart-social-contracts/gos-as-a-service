"""Pure helpers for Casals create_stand JSON arguments (no IC/basilisk imports)."""


def casals_placement_from_cfg(casals_cfg: dict) -> tuple[str, str]:
    subnet = (casals_cfg.get("subnet") or "").strip()
    subnet_type = (casals_cfg.get("subnet_type") or "").strip()
    return subnet, subnet_type


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
        args["subnet_type"] = subnet_type
    return args
