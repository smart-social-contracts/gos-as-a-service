"""Tests for deploy cycles estimation and preflight balance checks."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from gaas.cycles_plan import (
    REALM_OPS_MARGIN_CYCLES,
    REALMS_PER_DEPLOY_ASSUMPTION,
    WALLET_CREATE_CYCLES,
    _casals_backend_required,
    _realm_provisioning_budget,
    _wallet_create_cost,
    apply_headroom_topups,
    build_cycles_plan,
    canister_headroom,
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


def _descriptor(**overrides) -> Descriptor:
    data = {**SAMPLE_DESCRIPTOR, **overrides}
    return Descriptor.model_validate(data)


def test_wallet_required_all_canisters_missing() -> None:
    desc = _descriptor(canisters={})
    plan = build_cycles_plan(
        desc,
        "ic",
        wallet_balance=10_000_000_000_000,
        canister_balances={},
    )
    wallet = next(item for item in plan.items if item.label == "wallet")
    expected = sum(
        WALLET_CREATE_CYCLES + canister_headroom(name, desc)
        for name in PLATFORM_CANISTER_NAMES
    )
    assert wallet.required == expected
    assert len(plan.items) == 1


def test_wallet_required_partial_create_mix() -> None:
    canisters = {
        "file_registry": VALID_CANISTER_ID,
        "casals_backend": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
    }
    desc = _descriptor(canisters=canisters)
    casals_required = _casals_backend_required(desc)
    plan = build_cycles_plan(
        desc,
        "ic",
        wallet_balance=50_000_000_000_000,
        canister_balances={
            "file_registry": DEFAULT_THRESHOLD,
            "casals_backend": casals_required,
        },
    )
    wallet = next(item for item in plan.items if item.label == "wallet")
    expected = sum(
        _wallet_create_cost(name, desc)
        for name in PLATFORM_CANISTER_NAMES
        if name not in canisters
    )
    assert wallet.required == expected
    assert len(plan.items) == 1 + len(canisters)
    assert plan.ok


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
    assert file_reg.required == threshold
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
    assert file_reg.required == 3_000_000_000_000


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
    assert file_reg.shortfall == DEFAULT_THRESHOLD - 100_000_000_000
    assert wallet.required == file_reg.shortfall + sum(
        _wallet_create_cost(name, _descriptor(canisters=canisters))
        for name in PLATFORM_CANISTER_NAMES
        if name not in canisters
    )


def test_plan_ok_when_wallet_covers_canister_shortfall() -> None:
    desc = _descriptor(
        canisters={name: VALID_CANISTER_ID for name in PLATFORM_CANISTER_NAMES},
        multisig=MultisigConfig(backend_id="aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa"),
    )
    balances = {
        name: canister_headroom(name, desc) for name in PLATFORM_CANISTER_NAMES
    }
    balances["file_registry"] = 100_000_000_000
    shortfall = canister_headroom("file_registry", desc) - 100_000_000_000
    plan = build_cycles_plan(
        desc,
        "ic",
        wallet_balance=10_000_000_000_000,
        canister_balances=balances,
    )
    assert plan.ok
    wallet = next(item for item in plan.items if item.label == "wallet")
    assert wallet.required == shortfall
    assert [item.label for item in plan.pending_topups] == ["file_registry"]


def test_apply_headroom_topups_deposits_shortfalls() -> None:
    desc = _descriptor(canisters={"file_registry": VALID_CANISTER_ID})
    plan = build_cycles_plan(
        desc,
        "ic",
        wallet_balance=10_000_000_000_000,
        canister_balances={"file_registry": 100_000_000_000},
    )
    with patch("gaas.cycles_plan.dfx.top_up_canister") as mock_top_up:
        total = apply_headroom_topups(plan, "ic", identity="deployer")
    assert total == DEFAULT_THRESHOLD - 100_000_000_000
    mock_top_up.assert_called_once_with(
        VALID_CANISTER_ID,
        DEFAULT_THRESHOLD - 100_000_000_000,
        "ic",
        identity="deployer",
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
