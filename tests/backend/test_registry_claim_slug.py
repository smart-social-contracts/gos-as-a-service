"""Tests for federation slug claim with GOS metadata."""

import json

import _cdk as basilisk

from realm_registry_backend.api.registry import register_realm_by_caller
from realm_registry_backend.api.slugs import (
    DEFAULT_GGG_CONFORMANCE,
    DEFAULT_GOS_IMPLEMENTATION,
    DEFAULT_LOADER_PROFILE,
    claim_slug_by_caller,
    resolve_slug_json,
)
from realm_registry_backend.core.models import RealmRecord, SlugRecord

mock_ic = basilisk.ic


def _clear_slugs_and_realms():
    for slug in list(SlugRecord.instances()):
        slug.delete()
    for realm in list(RealmRecord.instances()):
        realm.delete()


def _register(backend_id: str, frontend_id: str):
    mock_ic.caller.return_value = backend_id
    result = register_realm_by_caller(
        "Test Realm",
        url="https://test.example",
        frontend_canister_id=frontend_id,
    )
    assert result["success"], result.get("error")


def test_claim_slug_stores_explicit_gos_metadata():
    _clear_slugs_and_realms()
    backend_id = "backend-gos-1"
    frontend_id = "frontend-gos-1"
    _register(backend_id, frontend_id)

    result = claim_slug_by_caller(
        "gos-realm",
        frontend_id,
        backend_id,
        gos_implementation="custom-gos",
        gos_version="9.9.9",
        ggg_conformance="2.0",
        loader_profile="custom-loader",
    )
    assert result["success"], result.get("error")

    payload = json.loads(resolve_slug_json("gos-realm"))
    assert payload["success"] is True
    assert payload["gos_implementation"] == "custom-gos"
    assert payload["gos_version"] == "9.9.9"
    assert payload["ggg_conformance"] == "2.0"
    assert payload["loader_profile"] == "custom-loader"


def test_claim_slug_defaults_without_gos_args():
    _clear_slugs_and_realms()
    backend_id = "backend-gos-2"
    frontend_id = "frontend-gos-2"
    _register(backend_id, frontend_id)

    result = claim_slug_by_caller("legacy-realm", frontend_id, backend_id)
    assert result["success"], result.get("error")

    payload = json.loads(resolve_slug_json("legacy-realm"))
    assert payload["success"] is True
    assert payload["gos_implementation"] == DEFAULT_GOS_IMPLEMENTATION
    assert payload["gos_version"] == ""
    assert payload["ggg_conformance"] == DEFAULT_GGG_CONFORMANCE
    assert payload["loader_profile"] == DEFAULT_LOADER_PROFILE
