"""Tests for ops-pool cycles pull / ensure / amount parsing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gaas.cycles_ops import (
    BRIDGE_CANISTER,
    PULL_HARD_LEAVE_CYCLES,
    PULL_OVERHEAD_CYCLES,
    ensure_canister_has,
    ensure_wallet_cycles,
    ensure_wallet_has,
    parse_cycles_amount,
    pull_from_casals_treasury,
    refill_children_from_casals,
    resolve_pull_source_paths,
)
from gaas.cycles_plan import WALLET_CREATE_CYCLES, WALLET_INITIAL_FUNDING, create_attach_cycles
from gaas.descriptor import CyclesConfig, Descriptor
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID

SOURCE_CASALS = "th7fr-bqaaa-aaaan-q6n4q-cai"


def _descriptor(**overrides) -> Descriptor:
    data = {**SAMPLE_DESCRIPTOR, **overrides}
    return Descriptor.model_validate(data)


def test_parse_cycles_amount() -> None:
    assert parse_cycles_amount("25t") == 25_000_000_000_000
    assert parse_cycles_amount("25TC") == 25_000_000_000_000
    assert parse_cycles_amount("1000") == 1000
    with pytest.raises(ValueError):
        parse_cycles_amount("nope")


def test_create_attach_casals_is_treasury_budget() -> None:
    desc = _descriptor(canisters={})
    assert create_attach_cycles("file_registry", desc) == WALLET_INITIAL_FUNDING
    assert create_attach_cycles("casals_backend", desc) > WALLET_INITIAL_FUNDING
    assert create_attach_cycles("casals_backend", desc) >= 16_000_000_000_000


def test_resolve_pull_from_sibling_name(tmp_path: Path) -> None:
    staging = tmp_path / "staging.json"
    demo = tmp_path / "demo.json"
    staging.write_text(
        Descriptor.model_validate(
            {
                **SAMPLE_DESCRIPTOR,
                "name": "staging",
                "domain": "staging.gos.earth",
                "canisters": {"casals_backend": SOURCE_CASALS},
            }
        ).to_pretty_json(),
        encoding="utf-8",
    )
    desc = _descriptor(
        name="demo",
        domain="demo.gos.earth",
        cycles=CyclesConfig(pull_from=["staging"], pull_leave_tc=40),
    )
    demo.write_text(desc.to_pretty_json(), encoding="utf-8")
    paths = resolve_pull_source_paths(desc, demo)
    assert paths == [staging.resolve()]


@patch("gaas.cycles_ops._casals_call")
@patch("gaas.cycles_ops._resolve_cycles_destination")
@patch("gaas.cycles_ops.dfx")
def test_pull_respects_leave_floor(
    mock_dfx: MagicMock,
    mock_dest: MagicMock,
    mock_call: MagicMock,
) -> None:
    mock_dfx.parse_canister_cycles_balance.return_value = 45_000_000_000_000
    mock_dfx.canister_status.return_value = MagicMock(raw="Cycles: 45_000_000_000_000")
    mock_dest.return_value = ("aaaaa-aaaaa-aaaaa-aaaaa-cai", True)
    mock_call.return_value = {"ok": True}

    moved = pull_from_casals_treasury(
        SOURCE_CASALS,
        25_000_000_000_000,
        leave=40_000_000_000_000,
        network="ic",
        identity="deployer",
    )
    assert moved == 5_000_000_000_000
    top_up = next(
        call for call in mock_call.call_args_list if call.args[1] == "top_up"
    )
    assert top_up.args[2]["amount"] == 5_000_000_000_000
    assert top_up.args[2]["canister"] == BRIDGE_CANISTER
    mock_dfx.refund_canister_to_ledger.assert_called_once()


@patch("gaas.cycles_ops._casals_call")
@patch("gaas.cycles_ops.dfx")
def test_pull_noop_when_at_leave_floor(
    mock_dfx: MagicMock,
    mock_call: MagicMock,
) -> None:
    mock_dfx.parse_canister_cycles_balance.return_value = 40_000_000_000_000
    mock_dfx.canister_status.return_value = MagicMock(raw="")
    moved = pull_from_casals_treasury(
        SOURCE_CASALS,
        25_000_000_000_000,
        leave=40_000_000_000_000,
        network="ic",
        identity="deployer",
    )
    assert moved == 0
    mock_call.assert_not_called()


@patch("gaas.cycles_ops.pull_from_casals_treasury")
@patch("gaas.cycles_ops.build_cycles_plan")
def test_ensure_wallet_pulls_shortfall_only(
    mock_plan: MagicMock,
    mock_pull: MagicMock,
    tmp_path: Path,
) -> None:
    from gaas.cycles_plan import CyclesLineItem, CyclesPlan

    short = CyclesPlan(
        network="ic",
        items=[
            CyclesLineItem(
                label="wallet",
                canister_id=None,
                required=20_000_000_000_000,
                available=3_000_000_000_000,
            )
        ],
    )
    covered = CyclesPlan(
        network="ic",
        items=[
            CyclesLineItem(
                label="wallet",
                canister_id=None,
                required=20_000_000_000_000,
                available=20_000_000_000_000,
            )
        ],
    )
    mock_plan.side_effect = [short, covered]
    mock_pull.return_value = 17_000_000_000_000

    staging = tmp_path / "staging.json"
    Descriptor.model_validate(
        {
            **SAMPLE_DESCRIPTOR,
            "name": "staging",
            "domain": "staging.gos.earth",
            "canisters": {"casals_backend": SOURCE_CASALS},
        }
    ).save(staging)
    desc = _descriptor(
        name="demo",
        domain="demo.gos.earth",
        cycles=CyclesConfig(pull_from=["staging"], pull_leave_tc=40),
    )
    path = tmp_path / "demo.json"
    desc.save(path)

    result = ensure_wallet_cycles(
        desc, network="ic", identity="deployer", descriptor_path=path
    )
    assert result["pulled"] == 17_000_000_000_000
    assert result["shortfall"] == 0
    assert result["dipped"] is False
    mock_pull.assert_called_once()
    assert mock_pull.call_args.args[1] == 17_000_000_000_000 + PULL_OVERHEAD_CYCLES


@patch("gaas.cycles_ops.pull_from_casals_treasury")
@patch("gaas.cycles_ops.build_cycles_plan")
def test_ensure_wallet_dips_leave_floor_for_last_mile(
    mock_plan: MagicMock,
    mock_pull: MagicMock,
    tmp_path: Path,
) -> None:
    from gaas.cycles_plan import CyclesLineItem, CyclesPlan

    short = CyclesPlan(
        network="ic",
        items=[
            CyclesLineItem(
                label="wallet",
                canister_id=None,
                required=27_550_000_000_000,
                available=25_702_000_000_000,
            )
        ],
    )
    covered = CyclesPlan(
        network="ic",
        items=[
            CyclesLineItem(
                label="wallet",
                canister_id=None,
                required=27_550_000_000_000,
                available=27_702_000_000_000,
            )
        ],
    )
    mock_plan.side_effect = [short, short, covered]
    mock_pull.side_effect = [0, 2_848_000_000_000]

    staging = tmp_path / "staging.json"
    Descriptor.model_validate(
        {
            **SAMPLE_DESCRIPTOR,
            "name": "staging",
            "domain": "staging.gos.earth",
            "canisters": {"casals_backend": SOURCE_CASALS},
        }
    ).save(staging)
    desc = _descriptor(
        name="demo",
        domain="demo.gos.earth",
        cycles=CyclesConfig(pull_from=["staging"], pull_leave_tc=40),
    )
    path = tmp_path / "demo.json"
    desc.save(path)

    result = ensure_wallet_cycles(
        desc, network="ic", identity="deployer", descriptor_path=path
    )
    assert result["pulled"] == 2_848_000_000_000
    assert result["shortfall"] == 0
    assert result["dipped"] is True
    assert mock_pull.call_count == 2
    first, second = mock_pull.call_args_list
    leftover = 27_550_000_000_000 - 25_702_000_000_000
    assert first.kwargs["leave"] == 40_000_000_000_000
    assert second.kwargs["leave"] == PULL_HARD_LEAVE_CYCLES
    assert PULL_HARD_LEAVE_CYCLES == 8_000_000_000_000
    assert second.args[1] == leftover + PULL_OVERHEAD_CYCLES


def test_ensure_skips_when_no_pull_from() -> None:
    desc = _descriptor(canisters={})
    with patch("gaas.cycles_ops.pull_from_casals_treasury") as mock_pull:
        with patch("gaas.cycles_ops.build_cycles_plan") as mock_plan:
            from gaas.cycles_plan import CyclesLineItem, CyclesPlan

            mock_plan.return_value = CyclesPlan(
                network="ic",
                items=[
                    CyclesLineItem(
                        label="wallet",
                        canister_id=None,
                        required=10,
                        available=0,
                    )
                ],
            )
            result = ensure_wallet_cycles(
                desc, network="ic", identity="deployer", descriptor_path=None
            )
    assert result["pulled"] == 0
    mock_pull.assert_not_called()


def test_wallet_create_constant_unchanged() -> None:
    assert WALLET_CREATE_CYCLES == 100_000_000_000


@patch("gaas.cycles_ops.pull_from_casals_treasury")
@patch("gaas.cycles_ops.dfx")
def test_ensure_wallet_has_pulls_until_required(
    mock_dfx: MagicMock,
    mock_pull: MagicMock,
    tmp_path: Path,
) -> None:
    mock_dfx.cycles_balance.side_effect = [
        700_000_000_000,
        3_700_000_000_000,
        3_700_000_000_000,
    ]
    mock_pull.return_value = 3_000_000_000_000
    staging = tmp_path / "staging.json"
    Descriptor.model_validate(
        {
            **SAMPLE_DESCRIPTOR,
            "name": "staging",
            "domain": "staging.gos.earth",
            "canisters": {"casals_backend": SOURCE_CASALS},
        }
    ).save(staging)
    desc = _descriptor(
        name="demo",
        domain="demo.gos.earth",
        cycles=CyclesConfig(pull_from=["staging"], pull_leave_tc=40),
    )
    path = tmp_path / "demo.json"
    desc.save(path)

    result = ensure_wallet_has(
        desc,
        network="ic",
        identity="deployer",
        descriptor_path=path,
        required=3_045_000_000_000,
    )
    assert result["pulled"] == 3_000_000_000_000
    assert result["shortfall"] == 0
    mock_pull.assert_called_once()
    assert mock_pull.call_args.args[1] == (
        3_045_000_000_000 - 700_000_000_000 + PULL_OVERHEAD_CYCLES
    )
    assert mock_pull.call_args.kwargs.get("destination") is None


@patch("gaas.cycles_ops._casals_call")
@patch("gaas.cycles_ops._resolve_cycles_destination")
@patch("gaas.cycles_ops.dfx")
def test_pull_to_destination_skips_holding_and_evicts_pool(
    mock_dfx: MagicMock,
    mock_dest: MagicMock,
    mock_call: MagicMock,
) -> None:
    dest = "onrok-rqaaa-aaaas-qgz7a-cai"
    mock_dfx.parse_canister_cycles_balance.return_value = 16_000_000_000_000
    mock_dfx.canister_status.return_value = MagicMock(raw="")
    mock_call.return_value = {"ok": True}

    moved = pull_from_casals_treasury(
        SOURCE_CASALS,
        1_412_000_000_000,
        leave=8_000_000_000_000,
        network="ic",
        identity="deployer",
        destination=dest,
    )
    assert moved == 1_412_000_000_000
    mock_dest.assert_not_called()
    mock_dfx.refund_canister_to_ledger.assert_not_called()
    methods = [call.args[1] for call in mock_call.call_args_list]
    assert "top_up" in methods
    assert "pool_remove" in methods
    pool = next(call for call in mock_call.call_args_list if call.args[1] == "pool_remove")
    assert pool.args[2]["canister_id"] == dest


@patch("gaas.cycles_ops.pull_from_casals_treasury")
@patch("gaas.cycles_ops.dfx")
def test_ensure_canister_has_skips_overhead(
    mock_dfx: MagicMock,
    mock_pull: MagicMock,
    tmp_path: Path,
) -> None:
    dest = "onrok-rqaaa-aaaas-qgz7a-cai"
    mock_dfx.parse_canister_cycles_balance.side_effect = [
        588_000_000_000,
        2_000_000_000_000,
        2_000_000_000_000,
    ]
    mock_dfx.canister_status.return_value = MagicMock(raw="")
    mock_pull.return_value = 1_412_000_000_000
    staging = tmp_path / "staging.json"
    Descriptor.model_validate(
        {
            **SAMPLE_DESCRIPTOR,
            "name": "staging",
            "domain": "staging.gos.earth",
            "canisters": {"casals_backend": SOURCE_CASALS},
        }
    ).save(staging)
    desc = _descriptor(
        name="demo",
        domain="demo.gos.earth",
        cycles=CyclesConfig(pull_from=["staging"], pull_leave_tc=40),
    )
    path = tmp_path / "demo.json"
    desc.save(path)

    result = ensure_canister_has(
        desc,
        dest,
        required=2_000_000_000_000,
        network="ic",
        identity="deployer",
        descriptor_path=path,
    )
    assert result["pulled"] == 1_412_000_000_000
    assert result["shortfall"] == 0
    mock_pull.assert_called_once()
    assert mock_pull.call_args.args[1] == 1_412_000_000_000
    assert mock_pull.call_args.kwargs["destination"] == dest


@patch("gaas.cycles_ops._casals_call")
def test_refill_children_from_casals_tops_tree_name(mock_call: MagicMock) -> None:
    mock_call.return_value = {"ok": True}
    dest_casals = "owusp-liaaa-aaaas-qgz5q-cai"
    moved = refill_children_from_casals(
        dest_casals,
        [("file_registry", "onrok-rqaaa-aaaas-qgz7a-cai", 1_412_000_000_000)],
        surplus=6_957_000_000_000,
        network="ic",
        identity="deployer",
    )
    assert moved == [("file_registry", 1_412_000_000_000)]
    top_up = mock_call.call_args
    assert top_up.args[1] == "top_up"
    assert top_up.args[2]["canister"] == "file-registry"
    assert top_up.args[2]["amount"] == 1_412_000_000_000
