"""Tests for registry version catalog publishing."""

from __future__ import annotations

import json
from unittest.mock import patch

from gaas.file_registry_client import ensure_version_catalog_entry, list_catalog_versions


@patch("gaas.file_registry_client.dfx.canister_call")
def test_list_catalog_versions_parses_response(mock_call) -> None:
    mock_call.return_value = json.dumps(
        {
            "success": True,
            "versions": [{"version": "0.3.1"}, {"version": "0.4.0"}],
        }
    )
    versions = list_catalog_versions("backend-id", "ic", identity="deployer")
    assert versions == {"0.3.1", "0.4.0"}


@patch("gaas.file_registry_client.dfx.canister_call")
def test_ensure_version_catalog_entry_publishes(mock_call) -> None:
    mock_call.side_effect = [
        json.dumps({"success": True, "versions": []}),
        'variant { Ok = "{\"success\":true,\"version\":\"0.3.1\"}" }',
    ]

    status = ensure_version_catalog_entry(
        "backend-id",
        "file-reg-id",
        "0.3.1",
        "wasm/realm-backend/0.3.1",
        "frontend/realm-assets/0.3.1",
        "realm_backend.wasm.gz",
        "deadbeef",
        "ic",
        identity="deployer",
    )

    assert status == "published"
    publish_call = mock_call.call_args_list[1]
    assert publish_call.args[1] == "publish_version"
    candid = publish_call.args[2]
    payload = json.loads(candid[2:-2].replace('\\"', '"'))
    assert payload == {
        "version": "0.3.1",
        "backend_wasm_url": "fileregistry://file-reg-id/wasm/realm-backend/0.3.1/realm_backend.wasm.gz",
        "frontend_tar_url": "fileregistry://file-reg-id/frontend/realm-assets/0.3.1",
        "backend_wasm_hash": "deadbeef",
        "frontend_tar_hash": "",
    }


@patch("gaas.file_registry_client.dfx.canister_call")
def test_ensure_version_catalog_entry_skips_when_present(mock_call) -> None:
    mock_call.return_value = json.dumps(
        {"success": True, "versions": [{"version": "0.3.1"}]}
    )

    status = ensure_version_catalog_entry(
        "backend-id",
        "file-reg-id",
        "0.3.1",
        "wasm/realm-backend/0.3.1",
        "frontend/realm-assets/0.3.1",
        "realm_backend.wasm.gz",
        "deadbeef",
        "ic",
        identity="deployer",
    )

    assert status == "skipped"
    mock_call.assert_called_once()
