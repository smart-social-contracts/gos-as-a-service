"""Tests for apply_env_inheritance manifest stamping."""

from realm_registry_backend.core.env_config import (
    apply_env_config,
    apply_env_inheritance,
    is_can_test_mode,
)
from realm_registry_backend.core.models import RegistryConfig
from realm_registry_backend.core.runtime_flags import apply_test_flags


def _clear_registry_config():
    for key in (
        "env:portal_url",
        "env:billing_url",
        "env:billing_service_principal",
        "env:can_test_mode",
        "env:open_mode",
        "portal_base_url",
        "portal_network",
        "flag:network",
        "flag:test_mode",
        "flag:test_mode_ii_bypass",
        "flag:test_mode_user_self_registration",
        "flag:test_mode_demo_data",
        "flag:test_mode_skip_terms",
        "flag:test_mode_skip_passport_zkproof",
        "flag:test_mode_skip_authentication",
    ):
        cfg = RegistryConfig[key]
        if cfg:
            cfg.delete()


def test_can_test_mode_true_defaults_test_flags():
    _clear_registry_config()
    apply_env_config({"can_test_mode": True})
    assert is_can_test_mode() is True

    manifest = apply_env_inheritance({})
    assert manifest["can_test_mode"] is True
    assert manifest["test_flags"]["test_mode"] is True
    assert manifest["test_flags"]["ii_bypass"] is True


def test_can_test_mode_true_copies_runtime_flags():
    _clear_registry_config()
    apply_env_config({"can_test_mode": True})
    apply_test_flags(
        {"test_mode": True, "ii_bypass": True, "demo_data": True},
        network="staging",
    )

    manifest = apply_env_inheritance({"network": "staging"})
    assert manifest["network"] == "staging"
    assert manifest["test_flags"]["test_mode"] is True
    assert manifest["test_flags"]["ii_bypass"] is True
    assert manifest["test_flags"]["demo_data"] is True


def test_can_test_mode_true_rewrites_ic_network():
    _clear_registry_config()
    apply_env_config({"can_test_mode": True, "portal_url": "https://test.gos.earth"})
    apply_test_flags({"test_mode": True, "ii_bypass": True}, network="test")

    manifest = apply_env_inheritance({"network": "ic"})
    assert manifest["network"] != "ic"
    assert manifest["network"] == "test"


def test_can_test_mode_true_derives_network_from_portal_url():
    _clear_registry_config()
    apply_env_config(
        {"can_test_mode": True, "portal_url": "https://test.gos.earth"}
    )

    manifest = apply_env_inheritance({"network": ""})
    assert manifest["network"] == "test"


def test_can_test_mode_false_strips_test_flags():
    _clear_registry_config()
    apply_env_config({"can_test_mode": False})

    manifest = apply_env_inheritance(
        {"network": "staging", "test_flags": {"test_mode": True, "ii_bypass": True}}
    )
    assert manifest["can_test_mode"] is False
    assert manifest["test_flags"] == {}


def test_overlay_merges_incoming_test_flags():
    _clear_registry_config()
    apply_env_config({"can_test_mode": True})
    apply_test_flags({"test_mode": True, "ii_bypass": True}, network="staging")

    manifest = apply_env_inheritance(
        {"network": "staging", "test_flags": {"demo_data": True}}
    )
    assert manifest["test_flags"]["test_mode"] is True
    assert manifest["test_flags"]["ii_bypass"] is True
    assert manifest["test_flags"]["demo_data"] is True

