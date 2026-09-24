"""Sheet-driven installer config (stable storage via InstallerConfig entity).

Every environment-specific value — product canister ids, the shared NFT
canister, the shared token ledgers — arrives through `configure`, called by the
Casals conductor from the `environments` block of casals.json. The canister
holds no per-network table of its own: such a table silently points a rebuilt
environment at a deleted canister.
"""

import json

from ic_python_db import Entity, Integer, String


class InstallerConfig(Entity):
    __alias__ = "key"
    key = String(max_length=16, default="singleton")
    provision_via_casals = Integer(default=0)
    casals_canister_id = String(max_length=64, default="")
    casals_section = String(max_length=64, default="Deployments")
    registry_principal = String(max_length=64, default="")
    file_registry_id = String(max_length=64, default="")
    marketplace_id = String(max_length=64, default="")
    nft_canister_id = String(max_length=64, default="")
    # {symbol: {ledger, indexer, decimals}} — shared ledgers the installer can
    # pass to a realm. The launch manifest does not select one.
    shared_tokens_json = String(max_length=4096, default="{}")
    portal_url = String(max_length=512, default="")
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


def configured_nft_canister_id() -> str:
    """The shared land-NFT canister, or "" when the environment has none."""
    return (get_config().nft_canister_id or "").strip()


def configured_shared_tokens() -> dict:
    """{symbol: {ledger, indexer, decimals}} from the sheet; {} when unset."""
    try:
        value = json.loads(get_config().shared_tokens_json or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def portal_url_to_origin(portal_url: str) -> str:
    """Extract scheme://host from a portal base or federation page URL."""
    url = (portal_url or "").strip().rstrip("/")
    if not url:
        return ""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    host = rest.split("/", 1)[0]
    return f"{scheme}://{host}"


def configured_portal_base(manifest=None):
    manifest = manifest or {}
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
    # The sheet is the only caller: a key that is present is applied verbatim,
    # "" included, so `converged_when: equals_args` can hold.
    if "file_registry_id" in params:
        cfg.file_registry_id = (params.get("file_registry_id") or "").strip()
    if "marketplace_id" in params:
        cfg.marketplace_id = (params.get("marketplace_id") or "").strip()
    if "nft_canister_id" in params:
        cfg.nft_canister_id = (params.get("nft_canister_id") or "").strip()
    if "shared_tokens" in params:
        tokens = params.get("shared_tokens") or {}
        if not isinstance(tokens, dict):
            raise ValueError("shared_tokens must be an object {symbol: {ledger, indexer, decimals}}")
        cfg.shared_tokens_json = json.dumps(tokens, sort_keys=True)
    if "casals_canister_id" in params:
        cfg.casals_canister_id = (params.get("casals_canister_id") or "").strip()
    if "casals_section" in params:
        cfg.casals_section = (params.get("casals_section") or "Deployments").strip()
    if "portal_url" in params:
        cfg.portal_url = (params.get("portal_url") or "").strip().rstrip("/")
    if "provision_via_casals" in params:
        cfg.provision_via_casals = 1 if params["provision_via_casals"] else 0
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
        "nft_canister_id": cfg.nft_canister_id or "",
        "shared_tokens": configured_shared_tokens(),
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
