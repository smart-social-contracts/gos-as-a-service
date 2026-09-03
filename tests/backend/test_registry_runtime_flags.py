#!/usr/bin/env python3
"""Tests for registry runtime test-mode flags."""

import json

from core.models import RegistryConfig
from core.runtime_flags import (
    apply_test_flags,
    default_assistant_experimental_notice,
    default_disable_card_billing,
    get_runtime_flags_payload,
    is_assistant_experimental_notice_enabled,
    is_card_billing_disabled,
    set_canister_config_from_json,
)


def _clear_card_billing_flag():
    for key in (
        "flag:test_mode_disable_card_billing",
        "flag:test_mode_assistant_experimental_notice",
        "flag:network",
        "env:portal_url",
        "env:casals_frontend",
    ):
        cfg = RegistryConfig[key]
        if cfg:
            cfg.delete()


def test_set_and_read_flags():
    apply_test_flags(
        {
            "test_mode": True,
            "ii_bypass": False,
            "user_self_registration": True,
        },
        network="staging",
    )
    payload = get_runtime_flags_payload()
    assert payload["success"] is True
    assert payload["network"] == "staging"
    assert payload["test_mode"] is True
    assert payload["test_mode_ii_bypass"] is False
    assert payload["test_mode_user_self_registration"] is True


def test_set_canister_config_json_wrapper():
    result = set_canister_config_from_json(
        json.dumps(
            {
                "network": "test",
                "test_flags": {"test_mode": True, "ii_bypass": True},
            }
        )
    )
    assert result["success"] is True
    payload = get_runtime_flags_payload()
    assert payload["network"] == "test"
    assert payload["test_mode_ii_bypass"] is True


def test_rejects_test_flags_on_mainnet():
    try:
        apply_test_flags({"test_mode": True}, network="ic")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "mainnet" in str(exc).lower()


def test_disable_card_billing_defaults_on_for_staging_and_demo():
    _clear_card_billing_flag()
    assert default_disable_card_billing("staging") is True
    assert default_disable_card_billing("demo") is True
    assert default_disable_card_billing("test") is False
    assert default_disable_card_billing("ic") is False

    apply_test_flags({"test_mode": True}, network="staging")
    payload = get_runtime_flags_payload()
    assert payload["test_mode_disable_card_billing"] is True
    assert is_card_billing_disabled() is True

    apply_test_flags({"test_mode": True}, network="demo")
    assert is_card_billing_disabled() is True

    apply_test_flags({"test_mode": True}, network="test")
    assert is_card_billing_disabled() is False


def test_disable_card_billing_explicit_override():
    _clear_card_billing_flag()
    apply_test_flags({"test_mode": True, "disable_card_billing": False}, network="staging")
    payload = get_runtime_flags_payload()
    assert payload["test_mode_disable_card_billing"] is False
    assert is_card_billing_disabled() is False

    apply_test_flags({"disable_card_billing": True}, network="test")
    payload = get_runtime_flags_payload()
    assert payload["test_mode_disable_card_billing"] is True
    assert is_card_billing_disabled() is True


def test_disable_card_billing_defaults_from_portal_host():
    _clear_card_billing_flag()
    from core.env_config import apply_env_config

    apply_env_config({"portal_url": "https://staging.gos.earth"})
    assert default_disable_card_billing("") is True
    apply_env_config({"portal_url": "https://test.gos.earth"})
    assert default_disable_card_billing("") is False


def test_set_canister_config_json_persists_disable_card_billing():
    _clear_card_billing_flag()
    result = set_canister_config_from_json(
        json.dumps(
            {
                "network": "staging",
                "test_flags": {
                    "test_mode": True,
                    "disable_card_billing": True,
                },
            }
        )
    )
    assert result["success"] is True
    payload = get_runtime_flags_payload()
    assert payload["network"] == "staging"
    assert payload["test_mode_disable_card_billing"] is True


def test_assistant_experimental_notice_defaults_on_for_staging_and_demo():
    _clear_card_billing_flag()
    assert default_assistant_experimental_notice("staging") is True
    assert default_assistant_experimental_notice("demo") is True
    assert default_assistant_experimental_notice("test") is False
    assert default_assistant_experimental_notice("ic") is False

    apply_test_flags({"test_mode": True}, network="staging")
    payload = get_runtime_flags_payload()
    assert payload["test_mode_assistant_experimental_notice"] is True
    assert is_assistant_experimental_notice_enabled() is True

    apply_test_flags({"test_mode": True}, network="demo")
    assert is_assistant_experimental_notice_enabled() is True

    apply_test_flags({"test_mode": True}, network="test")
    assert is_assistant_experimental_notice_enabled() is False


def test_assistant_experimental_notice_explicit_override():
    _clear_card_billing_flag()
    apply_test_flags(
        {"test_mode": True, "assistant_experimental_notice": False},
        network="staging",
    )
    payload = get_runtime_flags_payload()
    assert payload["test_mode_assistant_experimental_notice"] is False
    assert is_assistant_experimental_notice_enabled() is False

    apply_test_flags({"assistant_experimental_notice": True}, network="test")
    payload = get_runtime_flags_payload()
    assert payload["test_mode_assistant_experimental_notice"] is True
    assert is_assistant_experimental_notice_enabled() is True


def test_set_canister_config_json_persists_assistant_experimental_notice():
    _clear_card_billing_flag()
    result = set_canister_config_from_json(
        json.dumps(
            {
                "network": "staging",
                "test_flags": {
                    "test_mode": True,
                    "assistant_experimental_notice": True,
                },
            }
        )
    )
    assert result["success"] is True
    payload = get_runtime_flags_payload()
    assert payload["network"] == "staging"
    assert payload["test_mode_assistant_experimental_notice"] is True


def test_set_canister_config_json_persists_casals_frontend():
    _clear_card_billing_flag()
    result = set_canister_config_from_json(
        json.dumps({"casals_frontend_canister_id": "nfs6d-saaaa-aaaae-qkjya-cai"})
    )
    assert result["success"] is True
    payload = get_runtime_flags_payload()
    assert payload["casals_frontend_canister_id"] == "nfs6d-saaaa-aaaae-qkjya-cai"


if __name__ == "__main__":
    test_set_and_read_flags()
    test_set_canister_config_json_wrapper()
    test_rejects_test_flags_on_mainnet()
    test_disable_card_billing_defaults_on_for_staging_and_demo()
    test_disable_card_billing_explicit_override()
    test_disable_card_billing_defaults_from_portal_host()
    test_set_canister_config_json_persists_disable_card_billing()
    test_assistant_experimental_notice_defaults_on_for_staging_and_demo()
    test_assistant_experimental_notice_explicit_override()
    test_set_canister_config_json_persists_assistant_experimental_notice()
    test_set_canister_config_json_persists_casals_frontend()
    print("registry runtime_flags tests passed")
