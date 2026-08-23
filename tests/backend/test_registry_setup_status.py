"""Tests for realm listing status and setup-completion callback."""

import time

import _cdk as basilisk

from realm_registry_backend.api.registry import (
    complete_realm_setup,
    get_registered_realm,
    list_registered_realms,
    register_realm_by_caller,
)
from realm_registry_backend.core.models import RealmRecord

mock_ic = basilisk.ic


def _clear_realms():
    for realm in list(RealmRecord.instances()):
        realm.delete()


def _register(backend_id: str, name: str = "Setup Realm", url: str = "https://setup.example"):
    mock_ic.caller.return_value = backend_id
    result = register_realm_by_caller(name, url)
    assert result["success"], result.get("error")
    return result


def test_new_realm_registers_as_setup():
    _clear_realms()
    backend_id = "backend-setup-1"
    _register(backend_id)

    result = get_registered_realm(backend_id)
    assert result["success"], result.get("error")
    assert result["realm"]["listing_status"] == "setup"


def test_setup_completion_flips_to_live_when_caller_matches():
    _clear_realms()
    backend_id = "backend-setup-2"
    _register(backend_id)

    mock_ic.caller.return_value = backend_id
    result = complete_realm_setup(backend_id)
    assert result == {"success": True}

    realm = get_registered_realm(backend_id)
    assert realm["success"]
    assert realm["realm"]["listing_status"] == "live"


def test_setup_completion_allows_controller():
    _clear_realms()
    backend_id = "backend-setup-controller"
    _register(backend_id)

    mock_ic.caller.return_value = "controller-principal"
    mock_ic.is_controller.return_value = True
    result = complete_realm_setup(backend_id)
    assert result == {"success": True}

    realm = get_registered_realm(backend_id)
    assert realm["realm"]["listing_status"] == "live"
    mock_ic.is_controller.return_value = False


def test_setup_completion_rejects_wrong_caller():
    _clear_realms()
    backend_id = "backend-setup-3"
    _register(backend_id)

    mock_ic.caller.return_value = "wrong-backend-id"
    mock_ic.is_controller.return_value = False
    result = complete_realm_setup(backend_id)
    assert result["success"] is False
    assert "does not match" in result["error"]

    realm = get_registered_realm(backend_id)
    assert realm["realm"]["listing_status"] == "setup"


def test_setup_completion_rejects_unknown_realm():
    _clear_realms()
    backend_id = "backend-missing"
    mock_ic.caller.return_value = backend_id

    result = complete_realm_setup(backend_id)
    assert result["success"] is False
    assert "not found" in result["error"]


def test_existing_records_default_to_live():
    _clear_realms()
    backend_id = "backend-legacy-1"
    # Simulate a pre-migration record without listing_status persisted.
    RealmRecord(
        id=backend_id,
        name="Legacy Realm",
        url="https://legacy.example",
        created_at=time.time(),
        frontend_canister_id="fe-legacy",
    )

    result = get_registered_realm(backend_id)
    assert result["success"], result.get("error")
    assert result["realm"]["listing_status"] == "live"


def test_listing_responses_include_status():
    _clear_realms()
    setup_id = "backend-setup-list-1"
    live_id = "backend-setup-list-2"
    _register(setup_id, name="In Setup")
    _register(live_id, name="Already Live")

    mock_ic.caller.return_value = live_id
    complete_realm_setup(live_id)

    realms = {r["id"]: r for r in list_registered_realms()}
    assert realms[setup_id]["listing_status"] == "setup"
    assert realms[live_id]["listing_status"] == "live"
