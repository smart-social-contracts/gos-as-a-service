"""Tests for realm_installer descriptor configure helpers."""

import json
import os
import re
import sys

import _cdk as basilisk
import pytest

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

def _reset_installer_config():
    cfg = InstallerConfig["singleton"]
    if cfg:
        cfg.delete()
    list(InstallerConfig.instances())


def test_unconfigured_file_registry_is_empty_for_every_network():
    """No baked-in ids: they are re-minted per environment rebuild."""
    _reset_installer_config()
    for network in ("test", "demo", "staging", ""):
        assert configured_file_registry_id(network) == ""


def test_unconfigured_marketplace_is_empty_for_every_network():
    _reset_installer_config()
    for network in ("test", "demo", "staging", ""):
        assert configured_marketplace_id(network) == ""


def test_configure_ignores_empty_product_pointers():
    """gaas new configures the installer without knowing these ids; "" must not clear them."""
    _reset_installer_config()
    apply_installer_config({"file_registry_id": "fr-1", "marketplace_id": "mp-1"})
    apply_installer_config(
        {"file_registry_id": "", "marketplace_id": "", "portal_url": "https://p"}
    )
    payload = installer_config_payload()
    assert payload["file_registry_id"] == "fr-1"
    assert payload["marketplace_id"] == "mp-1"
    assert payload["portal_url"] == "https://p"


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


def test_require_casals_for_destroy_empty_raises():
    _reset_installer_config()
    from installer_config import CASALS_DESTROY_REQUIRED, require_casals_for_destroy

    with pytest.raises(RuntimeError, match=re.escape(CASALS_DESTROY_REQUIRED)):
        require_casals_for_destroy("")


def test_require_casals_for_destroy_missing_raises():
    _reset_installer_config()
    from installer_config import CASALS_DESTROY_REQUIRED, require_casals_for_destroy

    with pytest.raises(RuntimeError, match=re.escape(CASALS_DESTROY_REQUIRED)):
        require_casals_for_destroy()


def test_require_casals_for_destroy_explicit_id():
    _reset_installer_config()
    from installer_config import require_casals_for_destroy

    assert require_casals_for_destroy("casals-explicit") == "casals-explicit"


def test_require_casals_for_destroy_uses_stored_config():
    _reset_installer_config()
    from installer_config import require_casals_for_destroy

    apply_installer_config({"casals_canister_id": "stored-casals-id"})
    assert require_casals_for_destroy() == "stored-casals-id"
