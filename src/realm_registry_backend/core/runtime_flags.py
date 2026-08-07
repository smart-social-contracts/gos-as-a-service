"""Runtime test-mode flags for the realm registry backend.

Mirrors ``realm_backend/core/runtime_flags.py``: flags live in stable storage
(``RegistryConfig`` keys) and are set at runtime via ``set_canister_config_json``.
The registry frontend reads them through ``get_runtime_flags`` — no rebuild required.
"""

import json

from core.models import RegistryConfig

_NETWORK_KEY = "network"

# JSON keys in test_flags / test_flags_json → RegistryConfig key suffix.
_FLAG_MAP = {
    "test_mode": "test_mode",
    "ii_bypass": "test_mode_ii_bypass",
    "user_self_registration": "test_mode_user_self_registration",
    "demo_data": "test_mode_demo_data",
    "skip_terms": "test_mode_skip_terms",
    "skip_passport_zkproof": "test_mode_skip_passport_zkproof",
    "skip_authentication": "test_mode_skip_authentication",
}


def _config_key(flag_attr: str) -> str:
    return f"flag:{flag_attr}"


def get_network(default: str = "") -> str:
    cfg = RegistryConfig[_config_key(_NETWORK_KEY)]
    if cfg and cfg.value:
        return cfg.value
    return default


def get_flag(name: str, default: bool = False) -> bool:
    cfg = RegistryConfig[_config_key(name)]
    if cfg is None:
        return default
    return cfg.value.strip().lower() in ("true", "1", "yes")


def _set_flag(name: str, value: bool) -> None:
    key = _config_key(name)
    val = "true" if value else "false"
    cfg = RegistryConfig[key]
    if cfg:
        cfg.value = val
    else:
        RegistryConfig(key=key, value=val)


def apply_test_flags(flags: dict, network: str | None = None) -> None:
    """Persist test-mode flags. Rejects enabling any flag on mainnet (network=ic)."""
    effective_network = (network or get_network() or "").strip().lower()
    any_true = any(bool(v) for v in flags.values())
    if any_true and effective_network == "ic":
        raise ValueError("Test mode flags cannot be enabled on mainnet (network=ic)")

    if network is not None:
        key = _config_key(_NETWORK_KEY)
        cfg = RegistryConfig[key]
        if cfg:
            cfg.value = network
        else:
            RegistryConfig(key=key, value=network)

    for json_key, attr in _FLAG_MAP.items():
        if json_key in flags:
            _set_flag(attr, bool(flags[json_key]))


def get_runtime_flags_payload() -> dict:
    """Lightweight runtime flags for the registry frontend auth/join flows."""
    return {
        "success": True,
        "network": get_network(),
        "test_mode": get_flag("test_mode", False),
        "test_mode_ii_bypass": get_flag("test_mode_ii_bypass", False),
        "test_mode_user_self_registration": get_flag(
            "test_mode_user_self_registration", False
        ),
        "test_mode_demo_data": get_flag("test_mode_demo_data", False),
        "test_mode_skip_terms": get_flag("test_mode_skip_terms", False),
        "test_mode_skip_passport_zkproof": get_flag(
            "test_mode_skip_passport_zkproof", False
        ),
    }


def set_canister_config_from_json(args: str) -> dict:
    """Apply ``set_canister_config_json`` payload. Returns {success, message?, error?}."""
    params = json.loads(args) if args else {}
    flags_raw = params.get("test_flags_json")
    if flags_raw is None and isinstance(params.get("test_flags"), dict):
        flags_raw = params["test_flags"]
    elif isinstance(flags_raw, str):
        flags_raw = json.loads(flags_raw)

    network = params.get("network")
    if flags_raw:
        apply_test_flags(flags_raw, network=network)
    elif network is not None:
        apply_test_flags({}, network=network)

    return {"success": True, "message": "Registry config updated"}
