"""Can-test-mode credit skip and settlement behaviour."""

import json

import _cdk as basilisk

from realm_registry_backend.api.credits import create_deployment_hold, get_user_credits
from realm_registry_backend.core.env_config import (
    apply_env_config,
    is_can_test_mode,
    settle_deployment_succeeded,
)
from realm_registry_backend.core.models import DeploymentCreditHold, UserCredits

mock_ic = basilisk.ic


def _clear_credits():
    for hold in list(DeploymentCreditHold.instances()):
        hold.delete()
    for uc in list(UserCredits.instances()):
        uc.delete()


def test_can_test_mode_skips_hold_requirement_on_settlement():
    _clear_credits()
    apply_env_config({"can_test_mode": True})
    assert is_can_test_mode() is True

    out = settle_deployment_succeeded("job-open-1")
    assert out["success"] is True
    assert out["settlement"] == "skipped_can_test_mode"


def test_deprecated_open_mode_configure_still_skips_settlement():
    _clear_credits()
    apply_env_config({"open_mode": True})
    assert is_can_test_mode() is True

    out = settle_deployment_succeeded("job-legacy-1")
    assert out["success"] is True
    assert out["settlement"] == "skipped_can_test_mode"


def test_closed_mode_settlement_requires_hold():
    _clear_credits()
    apply_env_config({"can_test_mode": False})

    out = settle_deployment_succeeded("job-closed-1")
    assert out["success"] is False
    assert "not found" in out["error"].lower()


def test_credit_hold_still_works_when_closed():
    _clear_credits()
    apply_env_config({"can_test_mode": False})
    caller = "user-no-credits"
    cr = get_user_credits(caller)
    assert cr["credits"]["balance"] == 0

    hold = create_deployment_hold(caller, "job-1", 5, "test")
    assert hold["success"] is False
