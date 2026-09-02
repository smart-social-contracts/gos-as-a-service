"""Descriptor-driven environment config for the registry backend.

Stored in stable ``RegistryConfig`` keys. Set at install via init JSON and at
runtime via the controller-only ``configure`` update method.

Can test mode: only the explicit ``can_test_mode`` flag skips credit checks — a
missing ``billing_url`` does *not* imply can test mode (billing_url is
informational for frontends / external integrations).
"""

import json

from core.models import RegistryConfig

_PORTAL_URL_KEY = "env:portal_url"
_BILLING_URL_KEY = "env:billing_url"
_BILLING_SERVICE_PRINCIPAL_KEY = "env:billing_service_principal"
_CAN_TEST_MODE_KEY = "env:can_test_mode"
_OPEN_MODE_KEY = "env:open_mode"
_INSTALLER_ID_KEY = "env:installer_id"


def _truthy(val: str) -> bool:
    return (val or "").strip().lower() in ("true", "1", "yes")


def get_portal_url() -> str:
    cfg = RegistryConfig[_PORTAL_URL_KEY]
    return (cfg.value if cfg else "").strip().rstrip("/")


def get_billing_url() -> str:
    cfg = RegistryConfig[_BILLING_URL_KEY]
    return (cfg.value if cfg else "").strip()


def get_billing_service_principal() -> str:
    cfg = RegistryConfig[_BILLING_SERVICE_PRINCIPAL_KEY]
    return (cfg.value if cfg else "").strip()


def check_billing_service_caller(caller: str, action: str, *, log_warning=None) -> str | None:
    """Return an error message when *caller* may not mutate credits; else None.

    When ``billing_service_principal`` is unset, any caller is allowed (backward
    compat). When set, only that principal may call ``add_credits`` / ``deduct_credits``.
    """
    expected = get_billing_service_principal()
    if not expected:
        if log_warning:
            log_warning(
                "%s: billing_service_principal unset; allowing caller %s (backward compat)",
                action,
                caller,
            )
        return None
    if caller != expected:
        return f"Only the configured billing service ({expected}) may {action}"
    return None


def is_can_test_mode() -> bool:
    """Return True only when ``can_test_mode`` was explicitly enabled via configure/init."""
    cfg = RegistryConfig[_CAN_TEST_MODE_KEY]
    if cfg is not None and _truthy(cfg.value):
        return True
    cfg = RegistryConfig[_OPEN_MODE_KEY]
    return cfg is not None and _truthy(cfg.value)


def get_installer_id() -> str:
    cfg = RegistryConfig[_INSTALLER_ID_KEY]
    return (cfg.value if cfg else "").strip()


def apply_env_config(params: dict) -> None:
    """Persist env config fields present in *params* (all optional)."""
    if "portal_url" in params:
        val = (params.get("portal_url") or "").strip().rstrip("/")
        _set_key(_PORTAL_URL_KEY, val)
    if "billing_url" in params:
        val = (params.get("billing_url") or "").strip()
        _set_key(_BILLING_URL_KEY, val)
    if "billing_service_principal" in params:
        val = (params.get("billing_service_principal") or "").strip()
        _set_key(_BILLING_SERVICE_PRINCIPAL_KEY, val)
    can_test_mode_written = False
    if "can_test_mode" in params:
        val = "true" if params.get("can_test_mode") else "false"
        _set_key(_CAN_TEST_MODE_KEY, val)
        can_test_mode_written = True
    if "open_mode" in params:
        val = "true" if params.get("open_mode") else "false"
        if not can_test_mode_written:
            _set_key(_CAN_TEST_MODE_KEY, val)
        can_test_mode_written = True
    if can_test_mode_written:
        old_cfg = RegistryConfig[_OPEN_MODE_KEY]
        if old_cfg:
            old_cfg.delete()
    if "installer_id" in params:
        val = (params.get("installer_id") or "").strip()
        _set_key(_INSTALLER_ID_KEY, val)


def apply_env_config_from_json(args: str) -> dict:
    params = json.loads(args) if args else {}
    if not isinstance(params, dict):
        return {"success": False, "error": "Expected JSON object"}
    apply_env_config(params)
    return {"success": True, "message": "Environment config updated"}


def get_env_config_payload() -> dict:
    return {
        "success": True,
        "portal_url": get_portal_url(),
        "billing_url": get_billing_url(),
        "billing_service_principal": get_billing_service_principal(),
        "can_test_mode": is_can_test_mode(),
        "installer_id": get_installer_id(),
    }


def configure_registry(args_json: str, is_controller: bool) -> dict:
    """Apply configure payload; returns {Ok: json} or {Err: message}."""
    if not is_controller:
        return {"Err": "Only controllers can configure the registry"}
    result = apply_env_config_from_json(args_json)
    if not result.get("success"):
        return {"Err": result.get("error", "configure failed")}
    return {"Ok": json.dumps(get_env_config_payload())}


def settle_deployment_succeeded(job_id: str) -> dict:
    from api.credits import capture_deployment_hold

    hold_result = capture_deployment_hold(job_id, "Deployment completed")
    if hold_result.get("success"):
        return {"success": True, "job_id": job_id, "settlement": "captured"}
    if is_can_test_mode() and "not found" in (hold_result.get("error") or "").lower():
        return {"success": True, "job_id": job_id, "settlement": "skipped_can_test_mode"}
    return {"success": False, "error": hold_result.get("error", "capture failed")}


def settle_deployment_failed(job_id: str, reason: str) -> dict:
    from api.credits import release_deployment_hold

    hold_result = release_deployment_hold(job_id, f"Failed: {reason}")
    if hold_result.get("success"):
        return {"success": True, "job_id": job_id, "settlement": "released"}
    if is_can_test_mode() and "not found" in (hold_result.get("error") or "").lower():
        return {"success": True, "job_id": job_id, "settlement": "skipped_can_test_mode"}
    return {"success": False, "error": hold_result.get("error", "release failed")}


def _set_key(key: str, value: str) -> None:
    cfg = RegistryConfig[key]
    if cfg:
        cfg.value = value
    else:
        RegistryConfig(key=key, value=value)


_PRODUCTION_NETWORKS = frozenset({"ic", "production"})

# JSON keys in manifest test_flags → runtime_flags RegistryConfig attr suffix.
_TEST_FLAG_ATTRS = {
    "test_mode": "test_mode",
    "ii_bypass": "test_mode_ii_bypass",
    "user_self_registration": "test_mode_user_self_registration",
    "demo_data": "test_mode_demo_data",
    "skip_terms": "test_mode_skip_terms",
    "skip_passport_zkproof": "test_mode_skip_passport_zkproof",
    "skip_authentication": "test_mode_skip_authentication",
}

_PORTAL_HOST_NETWORKS = {
    "test.gos.earth": "test",
    "staging.gos.earth": "staging",
    "demo.gos.earth": "demo",
}


def _is_production_network(network: str) -> bool:
    return (network or "").strip().lower() in _PRODUCTION_NETWORKS


def _network_from_portal_url(url: str) -> str:
    lower = (url or "").strip().lower()
    for host, net in _PORTAL_HOST_NETWORKS.items():
        if host in lower:
            return net
    return ""


def _resolve_logical_network(manifest: dict) -> str:
    """Pick a non-mainnet logical network for can_test_mode manifests."""
    incoming = (manifest.get("network") or "").strip()
    if incoming and not _is_production_network(incoming):
        return incoming

    from core.runtime_flags import get_network

    registry_net = (get_network() or "").strip()
    if registry_net and not _is_production_network(registry_net):
        return registry_net

    portal_net = _network_from_portal_url(get_portal_url())
    if portal_net:
        return portal_net

    return "test"


def _inherited_test_flags_from_registry() -> dict:
    from core.runtime_flags import get_flag

    inherited: dict[str, bool] = {}
    for json_key, attr in _TEST_FLAG_ATTRS.items():
        if get_flag(attr, False):
            inherited[json_key] = True
    return inherited


def apply_env_inheritance(manifest: dict) -> dict:
    """Stamp registry env policy onto a deployment/upgrade manifest.

    Mutates and returns *manifest* so realms inherit ``can_test_mode`` and test
    flags from the registry — not from hardcoded network tables or stale realm
    network values (e.g. ``ic`` on test.gos.earth).

    Stored registry runtime flags are copied as-is. ``can_test_mode`` does not
    invent test_mode / ii_bypass.
    """
    manifest["can_test_mode"] = is_can_test_mode()

    if manifest["can_test_mode"]:
        manifest["network"] = _resolve_logical_network(manifest)

        inherited = _inherited_test_flags_from_registry()
        incoming = manifest.get("test_flags")
        merged = dict(inherited)
        if isinstance(incoming, dict):
            merged.update(incoming)
        manifest["test_flags"] = merged
    else:
        manifest.pop("test_flags", None)
        manifest["test_flags"] = {}

    return manifest
