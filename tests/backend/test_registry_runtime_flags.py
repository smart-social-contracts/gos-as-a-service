#!/usr/bin/env python3
"""Tests for registry runtime test-mode flags."""

import json

from core.runtime_flags import (
    apply_test_flags,
    get_runtime_flags_payload,
    set_canister_config_from_json,
)


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


if __name__ == "__main__":
    test_set_and_read_flags()
    test_set_canister_config_json_wrapper()
    test_rejects_test_flags_on_mainnet()
    print("registry runtime_flags tests passed")
