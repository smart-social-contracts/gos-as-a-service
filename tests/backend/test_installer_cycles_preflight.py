"""Tests for Casals cycles preflight before on-chain provisioning."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from cycles_preflight import (
    PREFLIGHT_FILE_REGISTRY_MIN_CYCLES,
    PREFLIGHT_OPS_MARGIN_CYCLES,
    PREFLIGHT_PER_CANISTER_CREATE_CYCLES,
    check_cycles_preflight,
    estimate_canister_creation_count,
    estimate_conductor_cycles_required,
    parse_cycles_report,
    resolve_file_registry_id,
)


CASALS_ID = "qthgp-3yaaa-aaaae-agveq-cai"
FR_ID = "uq2mu-kaaaa-aaaah-avqcq-cai"


def _manifest(*, deploy_scope: str = "both"):
    return {
        "deploy_scope": deploy_scope,
        "infra": {"file_registry_canister_id": FR_ID},
    }


def _report(*, treasury: int, file_registry: int | None = None):
    canisters = []
    if file_registry is not None:
        canisters.append({
            "section": "Infra",
            "stand": "platform",
            "name": "file-registry",
            "canister_id": FR_ID,
            "cycles": file_registry,
        })
    return {
        "treasury": {"balance": treasury, "spendable": treasury},
        "canisters": canisters,
    }


def test_typical_realm_requires_seven_trillion_with_baton():
    manifest = _manifest(deploy_scope="both")
    assert estimate_canister_creation_count(manifest, create_stand_baton=True) == 3
    required = estimate_conductor_cycles_required(manifest, create_stand_baton=True)
    assert required == 3 * PREFLIGHT_PER_CANISTER_CREATE_CYCLES + PREFLIGHT_OPS_MARGIN_CYCLES
    assert required == 7_000_000_000_000


def test_backend_only_without_baton_requires_five_trillion():
    manifest = _manifest(deploy_scope="backend_only")
    required = estimate_conductor_cycles_required(manifest, create_stand_baton=False)
    assert required == 1 * PREFLIGHT_PER_CANISTER_CREATE_CYCLES + PREFLIGHT_OPS_MARGIN_CYCLES


def test_resolve_file_registry_id_prefers_manifest_infra():
    manifest = {"infra": {"file_registry_canister_id": FR_ID}, "network": "test"}
    assert resolve_file_registry_id(manifest, network="test", configured_id="other-id") == FR_ID


def test_insufficient_conductor_returns_actionable_error():
    manifest = _manifest()
    required = estimate_conductor_cycles_required(manifest, create_stand_baton=True)
    report = _report(treasury=1_490_000_000_000, file_registry=2_000_000_000_000)
    err = check_cycles_preflight(
        report,
        casals_canister_id=CASALS_ID,
        required_conductor_cycles=required,
        file_registry_cycles=2_000_000_000_000,
        file_registry_id=FR_ID,
    )
    assert err is not None
    assert err.startswith("insufficient cycles:")
    assert CASALS_ID in err
    assert "shortfall" in err
    assert f"dfx cycles top-up {CASALS_ID}" in err
    assert "--network ic" in err


def test_insufficient_file_registry_returns_actionable_error():
    manifest = _manifest()
    required = estimate_conductor_cycles_required(manifest, create_stand_baton=True)
    report = _report(treasury=10_000_000_000_000, file_registry=100_000_000_000)
    err = check_cycles_preflight(
        report,
        casals_canister_id=CASALS_ID,
        required_conductor_cycles=required,
        file_registry_cycles=100_000_000_000,
        file_registry_id=FR_ID,
    )
    assert err is not None
    assert "file_registry" in err
    assert FR_ID in err
    assert f"dfx cycles top-up {FR_ID}" in err
    assert "needs 1.0T" in err


def test_sufficient_balances_pass_preflight():
    manifest = _manifest()
    required = estimate_conductor_cycles_required(manifest, create_stand_baton=True)
    report = _report(
        treasury=required + 1,
        file_registry=PREFLIGHT_FILE_REGISTRY_MIN_CYCLES + 1,
    )
    assert check_cycles_preflight(
        report,
        casals_canister_id=CASALS_ID,
        required_conductor_cycles=required,
        file_registry_cycles=PREFLIGHT_FILE_REGISTRY_MIN_CYCLES + 1,
        file_registry_id=FR_ID,
    ) is None


def test_missing_file_registry_row_skips_gracefully():
    manifest = _manifest()
    required = estimate_conductor_cycles_required(manifest, create_stand_baton=True)
    report = {"treasury": {"spendable": required + 1}, "canisters": []}
    assert check_cycles_preflight(
        report,
        casals_canister_id=CASALS_ID,
        required_conductor_cycles=required,
        file_registry_id="",
    ) is None


def test_parse_cycles_report_accepts_json_string():
    raw = parse_cycles_report('{"treasury":{"spendable":8000000000000}}')
    assert raw["treasury"]["spendable"] == 8_000_000_000_000
