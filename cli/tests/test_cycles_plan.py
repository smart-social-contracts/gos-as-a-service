"""Tests for deploy cycles estimation and preflight balance checks."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from gaas.cycles_plan import (
    FILE_REGISTRY_SEED_BUDGET,
    REALM_OPS_MARGIN_CYCLES,
    REALMS_PER_DEPLOY_ASSUMPTION,
    WALLET_CREATE_CYCLES,
    WALLET_INITIAL_FUNDING,
    _casals_backend_required,
    _realm_provisioning_budget,
    build_cycles_plan,
    casals_provision_floor,
    create_attach_cycles,
    print_cycles_plan,
    remediation_canister_top_up,
    remediation_wallet_convert,
    render_cycles_plan_table,
    wallet_convert_amount_icp,
)
from gaas.descriptor import CyclesConfig, Descriptor, MultisigConfig
from gaas.known import KNOWN_CANISTER_NAMES, PLATFORM_CANISTER_NAMES
from gaas.preflight import run_preflight
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID

DEFAULT_THRESHOLD = 2_000_000_000_000

# IC mainnet create with 0.5T --with-cycles fails: freeze + first 12 KiB
# memory grow needs ~26B more. Keep the attached amount above that floor.
def test_wallet_initial_funding_covers_ic_create_memory_grow() -> None:
    assert WALLET_INITIAL_FUNDING >= 1_250_000_000_000


def _descriptor(**overrides) -> Descriptor:
    data = {**SAMPLE_DESCRIPTOR, **overrides}
    return Descriptor.model_validate(data)


def test_wallet_required_all_canisters_missing() -> None:
    plan = build_cycles_plan(
        _descriptor(canisters={}),
        "ic",
        wallet_balance=10_000_000_000_000,
        canister_balances={},
    )
    wallet = next(item for item in plan.items if item.label == "wallet")
    per = WALLET_CREATE_CYCLES + WALLET_INITIAL_FUNDING
    desc = _descriptor(canisters={})
    extra = 0
    for name in PLATFORM_CANISTER_NAMES:
        extra += max(
            0, create_attach_cycles(name, desc) - WALLET_INITIAL_FUNDING
        )
    assert wallet.required == per * len(PLATFORM_CANISTER_NAMES) + extra
    assert extra == (
        max(0, _casals_backend_required(desc) - WALLET_INITIAL_FUNDING)
        + max(0, FILE_REGISTRY_SEED_BUDGET + DEFAULT_THRESHOLD - WALLET_INITIAL_FUNDING)
    )
    assert len(plan.items) == 1


def test_wallet_required_partial_create_mix() -> None:
    canisters = {
        "file_registry": VALID_CANISTER_ID,
        "casals_backend": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
    }
    plan = build_cycles_plan(
        _descriptor(canisters=canisters),
        "ic",
        wallet_balance=5_000_000_000_000,
        canister_balances={
            "file_registry": DEFAULT_THRESHOLD + FILE_REGISTRY_SEED_BUDGET,
            "casals_backend": _casals_backend_required(
                _descriptor(
                    canisters=canisters,
                    multisig=MultisigConfig(backend_id=None),
                )
            ),
        },
    )
    wallet = next(item for item in plan.items if item.label == "wallet")
    # file_registry is already in the descriptor, so it is not missing. Other
    # platform canisters still count toward wallet creation budget.
    missing = len([n for n in PLATFORM_CANISTER_NAMES if n not in canisters])
    assert wallet.required == missing * (WALLET_CREATE_CYCLES + WALLET_INITIAL_FUNDING)
    assert len(plan.items) == 1 + len(canisters)


def test_canister_headrooms_and_multisig_extra() -> None:
    canisters = {name: VALID_CANISTER_ID for name in KNOWN_CANISTER_NAMES}
    threshold = DEFAULT_THRESHOLD
    realm_budget = REALMS_PER_DEPLOY_ASSUMPTION * _realm_provisioning_budget(threshold)
    conductor_base = threshold + realm_budget

    plan_no_multisig = build_cycles_plan(
        _descriptor(canisters=canisters, multisig=MultisigConfig(backend_id=None)),
        "ic",
        wallet_balance=0,
        canister_balances={name: 10_000_000_000_000 for name in canisters},
    )
    casals = next(item for item in plan_no_multisig.items if item.label == "casals_backend")
    assert casals.required == conductor_base + threshold
    assert casals.required == _casals_backend_required(
        _descriptor(canisters=canisters, multisig=MultisigConfig(backend_id=None))
    )

    plan_with_multisig = build_cycles_plan(
        _descriptor(
            canisters=canisters,
            multisig=MultisigConfig(backend_id="aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa"),
        ),
        "ic",
        wallet_balance=0,
        canister_balances={name: 10_000_000_000_000 for name in canisters},
    )
    casals_ok = next(
        item for item in plan_with_multisig.items if item.label == "casals_backend"
    )
    assert casals_ok.required == conductor_base

    file_reg = next(item for item in plan_no_multisig.items if item.label == "file_registry")
    installer = next(
        item for item in plan_no_multisig.items if item.label == "realm_installer"
    )
    frontend = next(
        item for item in plan_no_multisig.items if item.label == "casals_frontend"
    )
    assert file_reg.required == threshold + FILE_REGISTRY_SEED_BUDGET
    assert installer.required == threshold
    assert frontend.required == threshold


def test_descriptor_threshold_tc_overrides_default_headroom() -> None:
    canisters = {"file_registry": VALID_CANISTER_ID}
    plan = build_cycles_plan(
        _descriptor(canisters=canisters, cycles=CyclesConfig(threshold_tc=3)),
        "ic",
        wallet_balance=0,
        canister_balances={"file_registry": 0},
    )
    file_reg = next(item for item in plan.items if item.label == "file_registry")
    assert file_reg.required == 3_000_000_000_000 + FILE_REGISTRY_SEED_BUDGET


def test_conductor_includes_realm_provisioning_budget() -> None:
    threshold = DEFAULT_THRESHOLD
    per_realm = 3 * threshold + REALM_OPS_MARGIN_CYCLES
    assert _realm_provisioning_budget(threshold) == per_realm
    assert per_realm == 7_000_000_000_000

    desc = _descriptor(
        canisters={"casals_backend": VALID_CANISTER_ID},
        multisig=MultisigConfig(backend_id="aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa"),
    )
    assert _casals_backend_required(desc) == threshold + (
        REALMS_PER_DEPLOY_ASSUMPTION * per_realm
    )
    assert _casals_backend_required(desc) == 16_000_000_000_000
    assert casals_provision_floor(desc) == threshold + per_realm
    assert casals_provision_floor(desc) == 9_000_000_000_000


def test_wallet_covers_adopted_frontend_shortfall() -> None:
    """Recreate-keep-frontend: wallet funds the portal top-up instead of failing."""
    canisters = {"realm_registry_frontend": VALID_CANISTER_ID}
    frontend_available = 200_000_000_000
    missing = len([n for n in PLATFORM_CANISTER_NAMES if n not in canisters])
    create_cost = missing * (WALLET_CREATE_CYCLES + WALLET_INITIAL_FUNDING)
    desc = _descriptor(canisters=canisters)
    for name in PLATFORM_CANISTER_NAMES:
        if name not in canisters:
            create_cost += max(
                0, create_attach_cycles(name, desc) - WALLET_INITIAL_FUNDING
            )
    topup = DEFAULT_THRESHOLD - frontend_available
    plan = build_cycles_plan(
        desc,
        "ic",
        wallet_balance=create_cost + topup,
        canister_balances={"realm_registry_frontend": frontend_available},
    )
    assert plan.ok
    wallet = next(item for item in plan.items if item.label == "wallet")
    assert wallet.required == create_cost + topup
    frontend = next(
        item for item in plan.items if item.label == "realm_registry_frontend"
    )
    assert frontend.shortfall == 0


def test_shortfall_detection_wallet_and_canister() -> None:
    canisters = {"file_registry": VALID_CANISTER_ID}
    plan = build_cycles_plan(
        _descriptor(canisters=canisters),
        "ic",
        wallet_balance=100_000_000_000,
        canister_balances={"file_registry": 100_000_000_000},
    )
    assert not plan.ok
    wallet = next(item for item in plan.items if item.label == "wallet")
    file_reg = next(item for item in plan.items if item.label == "file_registry")
    assert wallet.shortfall > 0
    assert file_reg.shortfall == (
        DEFAULT_THRESHOLD + FILE_REGISTRY_SEED_BUDGET - 100_000_000_000
    )


def test_remediation_commands() -> None:
    assert remediation_wallet_convert(1_300_000_000_000, "ic") == (
        "dfx cycles convert --amount=1.5 --network ic"
    )
    assert remediation_wallet_convert(500_000_000_000, "ic") == (
        "dfx cycles convert --amount=0.5 --network ic"
    )
    assert remediation_canister_top_up(VALID_CANISTER_ID, 250_000_000_000, "ic") == (
        f"dfx cycles top-up {VALID_CANISTER_ID} 250000000000 --network ic"
    )


def test_wallet_convert_rounds_up_to_half_icp() -> None:
    assert wallet_convert_amount_icp(1) == 0.5
    assert wallet_convert_amount_icp(1_000_000_000_000) == 1.0
    assert wallet_convert_amount_icp(1_000_000_000_001) == 1.5


def test_render_cycles_plan_table_columns() -> None:
    plan = build_cycles_plan(
        _descriptor(canisters={"file_registry": VALID_CANISTER_ID}),
        "ic",
        wallet_balance=1_000_000_000_000,
        canister_balances={"file_registry": DEFAULT_THRESHOLD},
    )
    table = render_cycles_plan_table(plan)
    assert table.title == "Cycles plan"
    assert len(table.columns) == 4


def test_print_cycles_plan_includes_remediation() -> None:
    canisters = {"casals_backend": VALID_CANISTER_ID}
    plan = build_cycles_plan(
        _descriptor(canisters=canisters, multisig=MultisigConfig(backend_id=None)),
        "ic",
        wallet_balance=0,
        canister_balances={"casals_backend": 0},
    )
    buffer = StringIO()
    print_cycles_plan(plan, Console(file=buffer, width=120, force_terminal=True))
    output = buffer.getvalue()
    assert "Suggested remediation" in output
    assert "dfx cycles convert" in output
    assert f"dfx cycles top-up {VALID_CANISTER_ID}" in output


@patch("gaas.preflight.dfx.identity_exists", return_value=True)
@patch("gaas.preflight.dfx.get_principal", return_value="aaaaa-aa")
@patch("gaas.preflight.build_cycles_plan")
def test_run_preflight_fails_on_shortfall(mock_build, _principal, _identity) -> None:
    from gaas.cycles_plan import CyclesLineItem, CyclesPlan

    mock_build.return_value = CyclesPlan(
        network="ic",
        items=[
            CyclesLineItem("wallet", None, 1_000_000_000_000, 100_000_000_000),
        ],
        remediations=["dfx cycles convert --amount=1 --network ic"],
    )
    report = run_preflight(
        _descriptor(),
        "deployer",
        "ic",
        console=Console(file=StringIO(), force_terminal=True),
    )
    assert not report.ok
    assert any(c.name == "cycles_plan" and not c.passed for c in report.checks)


@patch("gaas.preflight.dfx.identity_exists", return_value=True)
@patch("gaas.preflight.dfx.get_principal", return_value="aaaaa-aa")
@patch("gaas.preflight.build_cycles_plan")
def test_run_preflight_passes_when_plan_ok(mock_build, _principal, _identity) -> None:
    from gaas.cycles_plan import CyclesLineItem, CyclesPlan

    mock_build.return_value = CyclesPlan(
        network="ic",
        items=[
            CyclesLineItem("wallet", None, 0, 0),
        ],
    )
    report = run_preflight(
        _descriptor(),
        "deployer",
        "ic",
        console=Console(file=StringIO(), force_terminal=True),
    )
    assert report.ok
    assert any(c.name == "cycles_plan" and c.passed for c in report.checks)
