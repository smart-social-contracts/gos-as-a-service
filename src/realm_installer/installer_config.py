"""Descriptor-driven installer config (stable storage via InstallerConfig entity)."""

import json

from ic_python_db import Entity, Integer, String

_FILE_REGISTRY_IDS = {
    "staging": "iebdk-kqaaa-aaaau-agoxq-cai",
    "demo": "vi64l-3aaaa-aaaae-qj4va-cai",
    "test": "uq2mu-kaaaa-aaaah-avqcq-cai",
}

_MARKETPLACE_IDS = {
    "test": "2wldc-niaaa-aaaad-qlxga-cai",
    "demo": "ehyfg-wyaaa-aaaae-qg3qq-cai",
    "staging": "jji3o-uyaaa-aaaah-qreja-cai",
}


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
    baton_wasm_key = String(max_length=64, default="orchestration-baton")
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
    fid = (get_config().file_registry_id or "").strip()
    if fid:
        return fid
    return _FILE_REGISTRY_IDS.get((network or "").strip().lower(), "")


def configured_marketplace_id(network: str = "") -> str:
    mid = (get_config().marketplace_id or "").strip()
    if mid:
        return mid
    return _MARKETPLACE_IDS.get((network or "").strip().lower(), "")


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
    if "file_registry_id" in params:
        cfg.file_registry_id = (params.get("file_registry_id") or "").strip()
    if "marketplace_id" in params:
        cfg.marketplace_id = (params.get("marketplace_id") or "").strip()
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
        cfg.baton_wasm_key = (params.get("baton_wasm_key") or "orchestration-baton").strip()
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
