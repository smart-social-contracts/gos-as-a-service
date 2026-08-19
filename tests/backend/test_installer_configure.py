"""Tests for realm_installer descriptor configure helpers."""

import json
import os
import sys

import _cdk as basilisk

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from installer_config import (
    InstallerConfig,
    apply_installer_config,
    configured_file_registry_id,
    configured_marketplace_id,
    installer_config_payload,
)

mock_ic = basilisk.ic

_FILE_REGISTRY_IDS = {
    "staging": "iebdk-kqaaa-aaaau-agoxq-cai",
    "demo": "vi64l-3aaaa-aaaae-qj4va-cai",
    "test": "uq2mu-kaaaa-aaaah-avqcq-cai",
}

_MARKETPLACE_IDS = {
    "test": "2wldc-niaaa-aaaad-qlxga-cai",
    "demo": "ehyfg-wyaaa-aaaae-qg3qq-cai",
    "staging": "jji3o-uyaaa-aaaah-qreja-cai",
}


def _reset_installer_config():
    cfg = InstallerConfig["singleton"]
    if cfg:
        cfg.delete()
    list(InstallerConfig.instances())


def test_defaults_use_hardcoded_file_registry_per_network():
    _reset_installer_config()
    assert configured_file_registry_id("test") == _FILE_REGISTRY_IDS["test"]
    assert configured_file_registry_id("demo") == _FILE_REGISTRY_IDS["demo"]


def test_defaults_use_hardcoded_marketplace_per_network():
    _reset_installer_config()
    assert configured_marketplace_id("test") == _MARKETPLACE_IDS["test"]
    assert configured_marketplace_id("demo") == _MARKETPLACE_IDS["demo"]
    assert configured_marketplace_id("staging") == _MARKETPLACE_IDS["staging"]


def test_configure_overrides_file_registry_id():
    _reset_installer_config()
    apply_installer_config({"file_registry_id": "custom-fr-id"})
    assert configured_file_registry_id("test") == "custom-fr-id"
    payload = installer_config_payload()
    assert payload["file_registry_id"] == "custom-fr-id"


def test_configure_overrides_marketplace_id():
    _reset_installer_config()
    apply_installer_config({"marketplace_id": "custom-mp"})
    assert configured_marketplace_id("test") == "custom-mp"
    payload = installer_config_payload()
    assert payload["marketplace_id"] == "custom-mp"


def test_configure_maps_registry_backend_id():
    _reset_installer_config()
    apply_installer_config(
        {
            "registry_backend_id": "registry-principal-1",
            "casals_canister_id": "casals-1",
            "casals_section": "MySection",
            "portal_url": "https://portal.example",
            "cycle_threshold_cycles": 3_000_000_000_000,
        }
    )
    payload = installer_config_payload()
    assert payload["registry_backend_id"] == "registry-principal-1"
    assert payload["casals_canister_id"] == "casals-1"
    assert payload["casals_section"] == "MySection"
    assert payload["portal_url"] == "https://portal.example"
    assert payload["cycle_threshold_cycles"] == 3_000_000_000_000


def test_apply_installer_config_from_json():
    _reset_installer_config()
    from installer_config import apply_installer_config_from_json

    out = apply_installer_config_from_json(json.dumps({"file_registry_id": "configured-fr"}))
    assert out["success"] is True
    assert out["file_registry_id"] == "configured-fr"
    assert configured_file_registry_id("test") == "configured-fr"
