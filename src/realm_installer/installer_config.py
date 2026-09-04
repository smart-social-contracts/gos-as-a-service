"""Descriptor-driven installer config (stable storage via InstallerConfig entity)."""

import json

from ic_python_db import Entity, Integer, String

# No per-network default ids. The file registry and marketplace are Realms
# product canisters, re-minted whenever an environment is rebuilt, so a baked-in
# map silently points a fresh environment at a deleted canister — every package
# install then fails with "canister not found" instead of "not configured".
# Callers must get them from the manifest or from `configure`.


class InstallerConfig(Entity):
    __alias__ = "key"
    key = String(max_length=16, default="singleton")
    provision_via_casals = Integer(default=0)
    casals_canister_id = String(max_length=64, default="")
    casals_section = String(max_length=64, default="Deployments")
    registry_principal = String(max_length=64, default="")
    file_registry_id = String(max_length=64, default="")
    marketplace_id = String(max_length=64, default="")
    portal_url = String(max_length=512, default="")
    create_stand_baton = Integer(default=0)
    baton_wasm_key = String(max_length=64, default="orchestration-baton@1.3.0")
    cycle_threshold_cycles = Integer(default=2_000_000_000_000)


CASALS_DESTROY_REQUIRED = (
    "casals_canister_id is required to destroy canisters; "
    "refusing raw IC delete_canister (it burns leftover cycles)"
)


def require_casals_for_destroy(casals_id: str = "") -> str:
    cid = (casals_id or "").strip()
    if not cid:
        cid = (get_config().casals_canister_id or "").strip()
    if not cid:
        raise RuntimeError(CASALS_DESTROY_REQUIRED)
    return cid


def get_config() -> InstallerConfig:
    list(InstallerConfig.instances())
    cfg = InstallerConfig["singleton"]
    if cfg is None:
        cfg = InstallerConfig(key="singleton")
    return cfg


def configured_file_registry_id(network: str = "") -> str:
    """The configured file registry, or "" when nobody has configured one."""
    return (get_config().file_registry_id or "").strip()


def configured_marketplace_id(network: str = "") -> str:
    """The configured marketplace, or "" when nobody has configured one."""
    return (get_config().marketplace_id or "").strip()


def configured_portal_base(manifest=None):
    manifest = manifest or {}
    from ic_assets import portal_url_to_origin

    federation = manifest.get("federation") or {}
    url = (federation.get("portal_url") or "").strip()
    if url:
        return portal_url_to_origin(url)
    return (get_config().portal_url or "").strip().rstrip("/")


def apply_installer_config(params: dict) -> None:
    cfg = get_config()
    if "registry_backend_id" in params:
        cfg.registry_principal = (params.get("registry_backend_id") or "").strip()
    if "registry_principal" in params:
        cfg.registry_principal = (params.get("registry_principal") or "").strip()
    # Empty means "not provided" for the product pointers: `gaas new` and
    # `realms seed` both call configure, and only seed knows these ids. Treating ""
    # as "clear" let a later gaas re-run erase them.
    if (params.get("file_registry_id") or "").strip():
        cfg.file_registry_id = params["file_registry_id"].strip()
    if (params.get("marketplace_id") or "").strip():
        cfg.marketplace_id = params["marketplace_id"].strip()
    if "casals_canister_id" in params:
        cfg.casals_canister_id = (params.get("casals_canister_id") or "").strip()
    if "casals_section" in params:
        cfg.casals_section = (params.get("casals_section") or "Deployments").strip()
    if "portal_url" in params:
        cfg.portal_url = (params.get("portal_url") or "").strip().rstrip("/")
    if "provision_via_casals" in params:
        cfg.provision_via_casals = 1 if params["provision_via_casals"] else 0
    if "create_stand_baton" in params:
        cfg.create_stand_baton = 1 if params["create_stand_baton"] else 0
    if "baton_wasm_key" in params:
        cfg.baton_wasm_key = (params.get("baton_wasm_key") or "orchestration-baton@1.3.0").strip()
    if "cycle_threshold_cycles" in params:
        cfg.cycle_threshold_cycles = int(params.get("cycle_threshold_cycles") or 0)


def configured_cycle_threshold_cycles() -> int:
    value = int(get_config().cycle_threshold_cycles or 0)
    return value if value > 0 else 2_000_000_000_000


def installer_config_payload() -> dict:
    cfg = get_config()
    return {
        "success": True,
        "registry_backend_id": cfg.registry_principal or "",
        "file_registry_id": cfg.file_registry_id or "",
        "marketplace_id": cfg.marketplace_id or "",
        "casals_canister_id": cfg.casals_canister_id or "",
        "casals_section": cfg.casals_section or "Deployments",
        "portal_url": cfg.portal_url or "",
        "provision_via_casals": bool(cfg.provision_via_casals),
        "cycle_threshold_cycles": configured_cycle_threshold_cycles(),
    }


def apply_installer_config_from_json(args: str) -> dict:
    params = json.loads(args) if args else {}
    apply_installer_config(params)
    return installer_config_payload()
