"""Tests for conductor cycles snapshot priming."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from gaas.dfx import _parse_candid_string
from gaas.descriptor import Descriptor
from gaas.phases import (
    DeployContext,
    chunk_canister_names,
    collect_tree_canister_names,
    phase_prime_cycles_snapshot,
    verify_cycles_snapshot_covers_tree,
)
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID

CASALS_BACKEND_ID = "fffff-fffff-fffff-fffff-fffff-fff"


def _refresh_arg_canisters(arg: str) -> list[str]:
    return json.loads(_parse_candid_string(arg))["canisters"]


def _tree_with_canisters(count: int) -> dict:
    canisters = [
        {"name": f"canister-{index}", "canister_id": f"id-{index}"}
        for index in range(1, count + 1)
    ]
    return {
        "sections": [
            {
                "name": "Infra",
                "stands": [{"name": "platform", "canisters": canisters}],
            }
        ]
    }


def _snapshot_for_names(names: list[str], *, error_names: set[str] | None = None) -> dict:
    errors = error_names or set()
    rows = []
    ok = 0
    err = 0
    for name in names:
        if name in errors:
            rows.append({"name": name, "canister_id": f"cid-{name}", "status": "error"})
            err += 1
        else:
            rows.append(
                {"name": name, "canister_id": f"cid-{name}", "status": "ok", "cycles": 1}
            )
            ok += 1
    return {"totals": {"canisters": len(names), "ok": ok, "error": err}, "canisters": rows}


def test_chunk_canister_names_batches_of_three() -> None:
    names = [f"c{i}" for i in range(7)]
    batches = chunk_canister_names(names)
    assert batches == [names[0:3], names[3:6], names[6:7]]


def test_collect_tree_canister_names_skips_empty_ids() -> None:
    tree = {
        "sections": [
            {
                "name": "Infra",
                "stands": [
                    {
                        "name": "governance",
                        "canisters": [
                            {"name": "multisig", "canister_id": "aaaaa-aa"},
                            {"name": "pending", "canister_id": ""},
                            {"name": " ", "canister_id": "bbbbb-bb"},
                        ],
                    }
                ],
            }
        ]
    }
    assert collect_tree_canister_names(tree) == ["multisig"]


def test_verify_cycles_snapshot_passes_when_all_present() -> None:
    names = ["a", "b", "c"]
    snapshot = _snapshot_for_names(names)
    assert verify_cycles_snapshot_covers_tree(names, snapshot) == []


def test_verify_cycles_snapshot_returns_error_status_names() -> None:
    names = ["a", "b"]
    snapshot = _snapshot_for_names(names, error_names={"b"})
    assert verify_cycles_snapshot_covers_tree(names, snapshot) == ["b"]


def test_verify_cycles_snapshot_raises_when_name_missing() -> None:
    with pytest.raises(RuntimeError, match="missing conductor canisters"):
        verify_cycles_snapshot_covers_tree(["a", "b"], _snapshot_for_names(["a"]))


@patch("gaas.phases.dfx.canister_call")
@patch("gaas.phases.get_tree")
def test_phase_prime_cycles_snapshot_batches_seven_canisters(
    mock_get_tree: MagicMock,
    mock_call: MagicMock,
) -> None:
    names = [f"canister-{i}" for i in range(1, 8)]
    mock_get_tree.return_value = _tree_with_canisters(7)

    def refresh_side_effect(canister_id, method, arg, network, *, identity=None, query=False):
        del canister_id, network, identity, query
        if method == "get_cycles_cached":
            return json.dumps(_snapshot_for_names(names))
        payload = json.loads(_parse_candid_string(arg))
        batch = payload["canisters"]
        return json.dumps(_snapshot_for_names(batch))

    mock_call.side_effect = refresh_side_effect

    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"casals_backend": CASALS_BACKEND_ID}
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic")

    phase_prime_cycles_snapshot(desc, ctx)

    refresh_calls = [
        call
        for call in mock_call.call_args_list
        if call[0][1] == "refresh_canisters"
    ]
    assert len(refresh_calls) == 3
    assert _refresh_arg_canisters(refresh_calls[0][0][2]) == names[0:3]
    assert _refresh_arg_canisters(refresh_calls[1][0][2]) == names[3:6]
    assert _refresh_arg_canisters(refresh_calls[2][0][2]) == names[6:7]
    mock_call.assert_any_call(
        CASALS_BACKEND_ID,
        "get_cycles_cached",
        "()",
        "ic",
        identity="deployer",
        query=True,
    )


@patch("gaas.phases.dfx.canister_call")
@patch("gaas.phases.get_tree")
def test_phase_prime_cycles_snapshot_verification_passes(
    mock_get_tree: MagicMock,
    mock_call: MagicMock,
) -> None:
    names = ["canister-1", "canister-2"]
    mock_get_tree.return_value = _tree_with_canisters(2)

    def refresh_side_effect(canister_id, method, arg, network, *, identity=None, query=False):
        del canister_id, network, identity
        if query and method == "get_cycles_cached":
            return json.dumps(_snapshot_for_names(names))
        payload = json.loads(_parse_candid_string(arg))
        batch = payload["canisters"]
        return json.dumps(_snapshot_for_names(batch))

    mock_call.side_effect = refresh_side_effect

    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"casals_backend": CASALS_BACKEND_ID}
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic")

    phase_prime_cycles_snapshot(desc, ctx)


@patch("gaas.phases.dfx.canister_call")
@patch("gaas.phases.get_tree")
def test_phase_prime_cycles_snapshot_raises_when_snapshot_missing_canister(
    mock_get_tree: MagicMock,
    mock_call: MagicMock,
) -> None:
    names = ["canister-1", "canister-2"]
    mock_get_tree.return_value = _tree_with_canisters(2)

    def refresh_side_effect(canister_id, method, arg, network, *, identity=None, query=False):
        del canister_id, network, identity
        if query and method == "get_cycles_cached":
            return json.dumps(_snapshot_for_names(["canister-1"]))
        payload = json.loads(_parse_candid_string(arg))
        batch = payload["canisters"]
        return json.dumps(_snapshot_for_names(batch))

    mock_call.side_effect = refresh_side_effect

    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"casals_backend": CASALS_BACKEND_ID}
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic")

    with pytest.raises(RuntimeError, match="missing conductor canisters"):
        phase_prime_cycles_snapshot(desc, ctx)


@patch("gaas.phases.dfx.canister_call")
@patch("gaas.phases.get_tree")
def test_phase_prime_cycles_snapshot_warns_when_refresh_failed_and_row_missing(
    mock_get_tree: MagicMock,
    mock_call: MagicMock,
) -> None:
    names = ["canister-1", "canister-2"]
    mock_get_tree.return_value = _tree_with_canisters(2)

    def refresh_side_effect(canister_id, method, arg, network, *, identity=None, query=False):
        del canister_id, network, identity
        if query and method == "get_cycles_cached":
            return json.dumps(_snapshot_for_names(["canister-1"]))
        batch = _refresh_arg_canisters(arg)
        if "canister-2" in batch:
            return json.dumps(
                {
                    "ok": False,
                    "error": "Caller is not allowed to read the canister status",
                }
            )
        return json.dumps(_snapshot_for_names(batch))

    mock_call.side_effect = refresh_side_effect

    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"casals_backend": CASALS_BACKEND_ID}
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic")

    phase_prime_cycles_snapshot(desc, ctx)


@patch("gaas.phases.dfx.canister_call")
@patch("gaas.phases.get_tree")
def test_phase_prime_cycles_snapshot_empty_tree_skips(
    mock_get_tree: MagicMock,
    mock_call: MagicMock,
) -> None:
    mock_get_tree.return_value = {"sections": []}

    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"casals_backend": CASALS_BACKEND_ID}
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic")

    phase_prime_cycles_snapshot(desc, ctx)

    mock_call.assert_not_called()


@patch("gaas.phases.dfx.canister_call")
@patch("gaas.phases.get_tree")
def test_phase_prime_cycles_snapshot_retries_failed_batch_member(
    mock_get_tree: MagicMock,
    mock_call: MagicMock,
) -> None:
    names = ["canister-1", "canister-2", "canister-3"]
    mock_get_tree.return_value = _tree_with_canisters(3)

    def refresh_side_effect(canister_id, method, arg, network, *, identity=None, query=False):
        del canister_id, network, identity
        if query and method == "get_cycles_cached":
            return json.dumps(_snapshot_for_names(names))
        batch = _refresh_arg_canisters(arg)
        if batch == names:
            return json.dumps({"ok": False, "error": "batch failed"})
        if batch == ["canister-2"]:
            return json.dumps(_snapshot_for_names(["canister-2"]))
        return json.dumps(_snapshot_for_names(batch))

    mock_call.side_effect = refresh_side_effect

    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"casals_backend": CASALS_BACKEND_ID}
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic")

    phase_prime_cycles_snapshot(desc, ctx)

    individual_calls = [
        _refresh_arg_canisters(call[0][2])
        for call in mock_call.call_args_list
        if call[0][1] == "refresh_canisters"
    ]
    assert ["canister-2"] in individual_calls
