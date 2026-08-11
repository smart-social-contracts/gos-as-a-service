"""Tests for registry descriptor env config and slug portal resolution."""

import json

import _cdk as basilisk

from realm_registry_backend.api.registry import register_realm_by_caller
from realm_registry_backend.api.slugs import _portal_base_url, claim_slug_by_caller
from realm_registry_backend.core.env_config import (
    apply_env_config,
    apply_env_config_from_json,
    get_env_config_payload,
    get_portal_url,
    is_can_test_mode,
)
from realm_registry_backend.core.models import RegistryConfig, RealmRecord, SlugRecord

mock_ic = basilisk.ic


def _clear_env_config():
    for key in (
        "env:portal_url",
        "env:billing_url",
        "env:billing_service_principal",
        "env:can_test_mode",
        "env:open_mode",
        "portal_base_url",
        "portal_network",
    ):
        cfg = RegistryConfig[key]
        if cfg:
            cfg.delete()


def test_configure_persists_fields():
    _clear_env_config()
    result = apply_env_config_from_json(
        json.dumps(
            {
                "portal_url": "https://custom.example",
                "billing_url": "https://billing.example",
                "billing_service_principal": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
                "can_test_mode": True,
            }
        )
    )
    assert result["success"] is True
    payload = get_env_config_payload()
    assert payload["portal_url"] == "https://custom.example"
    assert payload["billing_url"] == "https://billing.example"
    assert payload["billing_service_principal"] == "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa"
    assert payload["can_test_mode"] is True
    assert "open_mode" not in payload


def test_configure_accepts_deprecated_open_mode_alias():
    _clear_env_config()
    apply_env_config({"open_mode": True})
    assert is_can_test_mode() is True
    payload = get_env_config_payload()
    assert payload["can_test_mode"] is True
    # Old stable key migrated away on write.
    assert RegistryConfig["env:open_mode"] is None


def test_add_credits_enforces_billing_service_principal():
    from realm_registry_backend.core.env_config import check_billing_service_caller

    _clear_env_config()
    billing_principal = "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa"
    apply_env_config({"billing_service_principal": billing_principal})

    denied = check_billing_service_caller("wrong-principal", "add credits")
    assert denied is not None
    assert "billing service" in denied.lower()
    assert check_billing_service_caller(billing_principal, "add credits") is None
    assert check_billing_service_caller(billing_principal, "deduct credits") is None


def test_add_credits_allows_any_caller_when_principal_unset():
    from realm_registry_backend.core.env_config import check_billing_service_caller

    _clear_env_config()
    assert check_billing_service_caller("any-caller", "add credits") is None


def test_can_test_mode_defaults_closed():
    _clear_env_config()
    assert is_can_test_mode() is False
    apply_env_config({"can_test_mode": False})
    assert is_can_test_mode() is False


def test_can_test_mode_reads_legacy_stable_key():
    _clear_env_config()
    RegistryConfig(key="env:open_mode", value="true")
    assert is_can_test_mode() is True


def test_portal_url_resolution_prefers_configured():
    _clear_env_config()
    apply_env_config({"portal_url": "https://configured.example"})
    assert _portal_base_url() == "https://configured.example"
    assert get_portal_url() == "https://configured.example"


def test_portal_url_falls_back_to_network_map():
    _clear_env_config()
    RegistryConfig(key="portal_network", value="test")
    assert _portal_base_url() == "https://test.gos.earth"


def test_claim_slug_uses_configured_portal_base():
    _clear_env_config()
    for slug in list(SlugRecord.instances()):
        slug.delete()
    for realm in list(RealmRecord.instances()):
        realm.delete()

    apply_env_config({"portal_url": "https://configured.example"})
    backend_id = "backend-portal-1"
    frontend_id = "frontend-portal-1"
    mock_ic.caller.return_value = backend_id
    register_realm_by_caller("Portal Realm", url="", frontend_canister_id=frontend_id)

    result = claim_slug_by_caller("my-slug", frontend_id, backend_id)
    assert result["success"], result.get("error")
    assert result["portal_url"] == "https://configured.example/r/my-slug"


def test_configure_requires_controller():
    from realm_registry_backend.core.env_config import configure_registry

    out = configure_registry(json.dumps({"can_test_mode": True}), is_controller=False)
    assert out["Err"] == "Only controllers can configure the registry"

    out = configure_registry(json.dumps({"portal_url": "https://ctrl.example"}), is_controller=True)
    assert "Ok" in out
    payload = json.loads(out["Ok"])
    assert payload["portal_url"] == "https://ctrl.example"
