"""Caller checks on the registry's slug, listing, credit and settlement endpoints."""

import pytest

import _cdk as basilisk

from realm_registry_backend.api.registry import register_realm_by_caller
from realm_registry_backend.api.slugs import claim_slug_by_caller, mark_pretty_hostname_status
from realm_registry_backend.core.env_config import (
    apply_env_config,
    check_billing_service_caller,
    settle_deployment_failed,
    settle_deployment_succeeded,
)
from realm_registry_backend.core.models import RealmRecord, SlugRecord

mock_ic = basilisk.ic

ANONYMOUS = "2vxsx-fae"
INSTALLER = "installer-principal"
BILLING = "billing-principal"
REALM = "realm-backend"
OTHER_REALM = "other-realm-backend"
STRANGER = "stranger-principal"
FRONTEND = "realm-frontend"
ATTACKER_FRONTEND = "attacker-frontend"


@pytest.fixture(autouse=True)
def _fresh():
    for slug in list(SlugRecord.instances()):
        slug.delete()
    for realm in list(RealmRecord.instances()):
        realm.delete()
    apply_env_config({
        "portal_url": "https://portal.example",
        "installer_id": INSTALLER,
        "billing_service_principal": "",
    })
    mock_ic.is_controller.return_value = False
    yield
    mock_ic.is_controller.return_value = False


def _call_as(caller: str, controller: bool = False):
    mock_ic.caller.return_value = caller
    mock_ic.is_controller.return_value = controller


def _register_realm(realm_id: str = REALM):
    _call_as(INSTALLER)
    result = register_realm_by_caller(
        "Realm", url="", frontend_canister_id=FRONTEND, realm_id_override=realm_id
    )
    assert result["success"], result.get("error")


# ── claim_slug (audit C1) ──────────────────────────────────────────────


@pytest.mark.parametrize("caller", [ANONYMOUS, STRANGER, OTHER_REALM])
def test_claim_slug_refuses_other_callers(caller):
    _register_realm()
    _call_as(caller)
    result = claim_slug_by_caller("victim", ATTACKER_FRONTEND, REALM)
    assert result["success"] is False
    assert "may not claim" in result["error"]
    assert SlugRecord["victim"] is None


@pytest.mark.parametrize("caller,controller", [(INSTALLER, False), (STRANGER, True)])
def test_claim_slug_creates_a_new_slug_for_the_installer_and_controller(caller, controller):
    _register_realm()
    _call_as(caller, controller)
    result = claim_slug_by_caller("my-realm", FRONTEND, REALM)
    assert result["success"], result.get("error")


def test_a_self_registered_realm_cannot_squat_a_pending_slug():
    _call_as(REALM)
    assert register_realm_by_caller("Attacker", url="", frontend_canister_id=ATTACKER_FRONTEND)["success"]
    result = claim_slug_by_caller("acme", ATTACKER_FRONTEND)
    assert result["success"] is False
    assert "may create a new slug" in result["error"]
    assert SlugRecord["acme"] is None

    _register_realm(OTHER_REALM)
    _call_as(INSTALLER)
    assert claim_slug_by_caller("acme", FRONTEND, OTHER_REALM)["success"]
    assert SlugRecord["acme"].realm_id == OTHER_REALM


def test_the_installer_creates_only_one_slug_per_realm():
    _claimed_slug()
    _call_as(INSTALLER)
    result = claim_slug_by_caller("second-slug", FRONTEND, REALM)
    assert result["success"] is False
    assert "already holds a slug" in result["error"]
    assert SlugRecord["second-slug"] is None


def test_a_controller_may_create_a_second_slug_for_a_realm():
    _claimed_slug()
    _call_as(STRANGER, controller=True)
    assert claim_slug_by_caller("second-slug", FRONTEND, REALM)["success"]


def test_claim_slug_defaults_the_realm_to_the_caller():
    _claimed_slug()
    _call_as(REALM)
    assert claim_slug_by_caller("my-realm", "new-frontend")["success"]
    assert SlugRecord["my-realm"].realm_id == REALM
    assert SlugRecord["my-realm"].frontend_canister_id == "new-frontend"


def _claimed_slug():
    _register_realm()
    _call_as(INSTALLER)
    assert claim_slug_by_caller("my-realm", FRONTEND, REALM)["success"]


def test_existing_slug_frontend_is_not_changed_by_the_installer():
    _claimed_slug()
    _call_as(INSTALLER)
    result = claim_slug_by_caller("my-realm", ATTACKER_FRONTEND, REALM)
    assert result["success"] is False
    assert "change the frontend" in result["error"]
    assert SlugRecord["my-realm"].frontend_canister_id == FRONTEND
    assert RealmRecord[REALM].frontend_canister_id == FRONTEND


@pytest.mark.parametrize("caller,controller", [(REALM, False), (STRANGER, True)])
def test_existing_slug_frontend_is_changed_by_the_realm_or_a_controller(caller, controller):
    _claimed_slug()
    _call_as(caller, controller)
    assert claim_slug_by_caller("my-realm", "new-frontend", REALM)["success"]
    assert SlugRecord["my-realm"].frontend_canister_id == "new-frontend"


def test_installer_may_reclaim_an_existing_slug_with_the_same_frontend():
    _claimed_slug()
    _call_as(INSTALLER)
    assert claim_slug_by_caller("my-realm", FRONTEND, REALM)["success"]


# ── add_credits / deduct_credits (audit H1) ────────────────────────────


@pytest.mark.parametrize("caller", [ANONYMOUS, STRANGER, INSTALLER])
def test_credits_refuse_everyone_but_controllers_when_billing_principal_unset(caller):
    denied = check_billing_service_caller(caller, "add credits", is_controller=False)
    assert denied is not None
    assert "controller" in denied


def test_credits_allow_a_controller_when_billing_principal_unset():
    assert check_billing_service_caller(STRANGER, "add credits", is_controller=True) is None


def test_credits_allow_only_the_billing_principal_when_set():
    apply_env_config({"billing_service_principal": BILLING})
    assert check_billing_service_caller(BILLING, "add credits", is_controller=False) is None
    for caller in (ANONYMOUS, STRANGER):
        assert check_billing_service_caller(caller, "add credits", is_controller=False) is not None


# ── deployment_succeeded / deployment_failed (audit H2) ────────────────


@pytest.mark.parametrize("caller", [ANONYMOUS, STRANGER, REALM])
def test_settlement_refuses_other_callers(caller):
    for out in (
        settle_deployment_succeeded("job-1", caller),
        settle_deployment_failed("job-1", "reason", caller),
    ):
        assert out["success"] is False
        assert "installer" in out["error"]


def test_settlement_refuses_everyone_when_no_installer_is_configured():
    apply_env_config({"installer_id": ""})
    assert settle_deployment_succeeded("job-1", "")["success"] is False
    assert settle_deployment_failed("job-1", "reason", "")["success"] is False


def test_settlement_reaches_the_hold_for_the_installer():
    # No hold exists for this job, so the installer gets past the caller check
    # to the "not found" error of the hold lookup.
    apply_env_config({"can_test_mode": False})
    for out in (
        settle_deployment_succeeded("job-no-hold", INSTALLER),
        settle_deployment_failed("job-no-hold", "reason", INSTALLER),
    ):
        assert out["success"] is False
        assert "not found" in out["error"].lower()


# ── register_realm and set_pretty_hostname_status (audit M8) ───────────


def test_register_realm_refuses_a_record_for_another_realm():
    for caller in (ANONYMOUS, STRANGER):
        _call_as(caller)
        result = register_realm_by_caller("Spoof", realm_id_override=REALM)
        assert result["success"] is False
    assert RealmRecord[REALM] is None


def test_register_realm_allows_the_installer_and_controllers_to_register_for_a_realm():
    _call_as(INSTALLER)
    assert register_realm_by_caller("Via installer", realm_id_override=REALM)["success"]
    _call_as(STRANGER, controller=True)
    assert register_realm_by_caller("Via controller", realm_id_override=OTHER_REALM)["success"]


def test_register_realm_lets_a_realm_register_itself():
    _call_as(REALM)
    assert register_realm_by_caller("Self", url="https://self.example")["success"]
    assert RealmRecord[REALM].name == "Self"


def test_pretty_hostname_status_is_for_controllers():
    _claimed_slug()
    result = mark_pretty_hostname_status("my-realm", "live", is_controller=False)
    assert result["success"] is False
    assert SlugRecord["my-realm"].pretty_hostname_status == "pending"
    assert mark_pretty_hostname_status("my-realm", "live", is_controller=True)["success"]
    assert SlugRecord["my-realm"].pretty_hostname_status == "live"

