"""Descriptor-driven environment config for the registry backend.

Stored in stable ``RegistryConfig`` keys. Set at install via init JSON and at
runtime via the controller-only ``configure`` update method.

Open mode: only the explicit ``open_mode`` flag skips credit checks — a missing
``billing_url`` does *not* imply open mode (billing_url is informational for
frontends / external integrations).
"""

import json

from core.models import RegistryConfig

_PORTAL_URL_KEY = "env:portal_url"
_BILLING_URL_KEY = "env:billing_url"
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


def is_open_mode() -> bool:
    """Return True only when ``open_mode`` was explicitly enabled via configure/init."""
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
    if "open_mode" in params:
        val = "true" if params.get("open_mode") else "false"
        _set_key(_OPEN_MODE_KEY, val)
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
        "open_mode": is_open_mode(),
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
    if is_open_mode() and "not found" in (hold_result.get("error") or "").lower():
        return {"success": True, "job_id": job_id, "settlement": "skipped_open_mode"}
    return {"success": False, "error": hold_result.get("error", "capture failed")}


def settle_deployment_failed(job_id: str, reason: str) -> dict:
    from api.credits import release_deployment_hold

    hold_result = release_deployment_hold(job_id, f"Failed: {reason}")
    if hold_result.get("success"):
        return {"success": True, "job_id": job_id, "settlement": "released"}
    if is_open_mode() and "not found" in (hold_result.get("error") or "").lower():
        return {"success": True, "job_id": job_id, "settlement": "skipped_open_mode"}
    return {"success": False, "error": hold_result.get("error", "release failed")}


def _set_key(key: str, value: str) -> None:
    cfg = RegistryConfig[key]
    if cfg:
        cfg.value = value
    else:
        RegistryConfig(key=key, value=value)
