"""Tests for gaas destroy (Casals drain-then-delete)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gaas.descriptor import Descriptor
from gaas.destroy import (
    CASALS_DESTROY_TOPUP,
    CONDUCTOR_DELETE_MAX,
    EVAC_MIN_RESERVE,
    FRONTEND_NAME,
    HOLDING_ENV,
    also_destroy_descriptor_canisters,
    clear_destroyed_descriptor_ids,
    destroy_except_frontend,
    destroy_via_casals,
    ensure_casals_controller,
    evacuate_treasury_to_wallet,
    run_destroy_orchestra_loop,
)
from gaas.dfx import CanisterStatus, DfxError, _parse_candid_string
from gaas.main import app
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID

runner = CliRunner()
CASALS_ID = "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb"
FRONTEND_ID = "77243-aqaaa-aaaau-aggza-cai"
WALLET_ID = "wwwww-wwwww-wwwww-wwwww-wwwww-www"
REGISTRY_ID = "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa"
INSTALLER_ID = "iiiii-iiiii-iiiii-iiiii-iiiii-iii"
DEPLOYER_PRINCIPAL = "ddddd-ddddd-ddddd-ddddd-ddddd-ddd"


def _destroy_descriptor(tmp_path: Path, *, canisters: dict[str, str] | None = None) -> Path:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = canisters or {
        "casals_backend": CASALS_ID,
        "realm_registry_backend": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
    }
    path = tmp_path / "env.gaas.json"
    Descriptor.model_validate(data).save(path)
    return path


@patch("gaas.destroy.dfx.canister_call")
def test_destroy_stand_calls_destroy_stand(mock_call: MagicMock, tmp_path: Path) -> None:
    path = _destroy_descriptor(tmp_path)
    desc = Descriptor.load(path)
    mock_call.return_value = json.dumps({"ok": True, "total_cycles_reclaimed": 500})

    result = destroy_via_casals(
        desc,
        network="ic",
        identity="deployer",
        stand="my-stand",
    )

    assert result["ok"] is True
    mock_call.assert_called_once()
    casals_id, method, arg, network = mock_call.call_args[0]
    assert casals_id == CASALS_ID
    assert method == "destroy_stand"
    assert network == "ic"
    assert json.loads(_parse_candid_string(arg)) == {"stand": "my-stand"}


@patch("gaas.destroy.dfx.canister_status")
@patch("gaas.destroy.dfx.canister_call")
def test_destroy_canister_id_checks_controllers_then_calls(
    mock_call: MagicMock,
    mock_status: MagicMock,
    tmp_path: Path,
) -> None:
    path = _destroy_descriptor(tmp_path)
    desc = Descriptor.load(path)
    target = VALID_CANISTER_ID
    mock_status.return_value = CanisterStatus(
        canister_id=target,
        status="running",
        raw="",
        controllers=(CASALS_ID,),
    )
    mock_call.return_value = json.dumps({"ok": True, "cycles_reclaimed": 1000})

    result = destroy_via_casals(
        desc,
        network="ic",
        identity="deployer",
        canister_id=target,
    )

    assert result["ok"] is True
    mock_status.assert_called_once_with(target, "ic", identity="deployer")
    mock_call.assert_called_once()
    _, method, arg, _ = mock_call.call_args[0]
    assert method == "destroy_canister"
    assert json.loads(_parse_candid_string(arg)) == {"canister_id": target}


@patch("gaas.destroy.dfx.canister_status")
def test_destroy_refuses_platform_canister_without_allow_platform(
    mock_status: MagicMock,
    tmp_path: Path,
) -> None:
    platform_id = "ccccc-ccccc-ccccc-ccccc-ccccc-ccc"
    canisters = {"casals_backend": CASALS_ID, "casals_frontend": platform_id}
    path = _destroy_descriptor(tmp_path, canisters=canisters)
    desc = Descriptor.load(path)

    with pytest.raises(RuntimeError, match="platform canister"):
        destroy_via_casals(
            desc,
            network="ic",
            identity="deployer",
            canister_id=platform_id,
        )
    mock_status.assert_not_called()


@patch("gaas.destroy.dfx.canister_status")
@patch("gaas.destroy.dfx.canister_call")
def test_destroy_allows_platform_canister_with_allow_platform(
    mock_call: MagicMock,
    mock_status: MagicMock,
    tmp_path: Path,
) -> None:
    platform_id = "ccccc-ccccc-ccccc-ccccc-ccccc-ccc"
    canisters = {"casals_backend": CASALS_ID, "casals_frontend": platform_id}
    path = _destroy_descriptor(tmp_path, canisters=canisters)
    desc = Descriptor.load(path)
    mock_status.return_value = CanisterStatus(
        canister_id=platform_id,
        status="running",
        raw="",
        controllers=(CASALS_ID,),
    )
    mock_call.return_value = json.dumps({"ok": True})

    destroy_via_casals(
        desc,
        network="ic",
        identity="deployer",
        canister_id=platform_id,
        allow_platform=True,
    )

    mock_call.assert_called_once()


@patch("gaas.destroy.dfx.canister_status")
def test_destroy_refuses_when_casals_not_controller(mock_status: MagicMock, tmp_path: Path) -> None:
    path = _destroy_descriptor(tmp_path)
    desc = Descriptor.load(path)
    target = VALID_CANISTER_ID
    mock_status.return_value = CanisterStatus(
        canister_id=target,
        status="running",
        raw="",
        controllers=("other-controller-id",),
    )

    with pytest.raises(RuntimeError, match="not a controller"):
        destroy_via_casals(
            desc,
            network="ic",
            identity="deployer",
            canister_id=target,
        )


@patch("gaas.main.typer.confirm", return_value=False)
@patch("gaas.main.destroy_via_casals")
def test_destroy_cli_without_yes_aborts(
    mock_destroy: MagicMock,
    _mock_confirm: MagicMock,
    tmp_path: Path,
) -> None:
    path = _destroy_descriptor(tmp_path)
    result = runner.invoke(
        app,
        ["destroy", str(path), "--identity", "deployer", "--stand", "foo"],
    )
    assert result.exit_code == 1
    mock_destroy.assert_not_called()


@patch("gaas.main.destroy_via_casals")
def test_destroy_cli_yes_stand(mock_destroy: MagicMock, tmp_path: Path) -> None:
    path = _destroy_descriptor(tmp_path)
    mock_destroy.return_value = {"ok": True, "total_cycles_reclaimed": 42_000}

    result = runner.invoke(
        app,
        ["destroy", str(path), "--identity", "deployer", "--yes", "--stand", "foo"],
    )

    assert result.exit_code == 0, result.output
    mock_destroy.assert_called_once()
    assert mock_destroy.call_args.kwargs["stand"] == "foo"
    assert "Cycles reclaimed" in result.output


def _full_descriptor(tmp_path: Path) -> Descriptor:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "casals_backend": CASALS_ID,
        FRONTEND_NAME: FRONTEND_ID,
        "realm_registry_backend": REGISTRY_ID,
        "realm_installer": INSTALLER_ID,
        "casals_frontend": "ccccc-ccccc-ccccc-ccccc-ccccc-ccc",
    }
    data["multisig"] = {"backend_id": REGISTRY_ID, "signers": [], "threshold": 1}
    path = tmp_path / "env.gaas.json"
    desc = Descriptor.model_validate(data)
    desc.save(path)
    return Descriptor.load(path)


@patch("gaas.destroy.dfx.delete_dust_canister")
@patch("gaas.destroy.dfx.canister_status")
@patch("gaas.destroy.dfx.get_principal")
@patch("gaas.destroy.dfx.get_wallet")
@patch("gaas.destroy.dfx.canister_call")
@patch("gaas.destroy.ensure_casals_controller")
def test_destroy_except_frontend_orchestra_loop_and_extras(
    mock_ensure: MagicMock,
    mock_call: MagicMock,
    mock_wallet: MagicMock,
    mock_principal: MagicMock,
    mock_status: MagicMock,
    mock_dust_delete: MagicMock,
    tmp_path: Path,
) -> None:
    desc = _full_descriptor(tmp_path)
    mock_wallet.return_value = WALLET_ID
    mock_principal.return_value = DEPLOYER_PRINCIPAL

    orchestra_batches = [
        json.dumps({"ok": True, "destroyed": [{"canister_id": "x1"}], "remaining": 1, "done": False, "cycles_reclaimed": 10}),
        json.dumps({"ok": True, "destroyed": [{"canister_id": "x2"}], "remaining": 0, "done": True, "cycles_reclaimed": 20}),
    ]
    side_effects = [
        *orchestra_batches,
        json.dumps({"ok": True, "cycles_reclaimed": 5}),  # registry destroy
        json.dumps({"ok": True, "cycles_reclaimed": 3}),  # installer destroy
        json.dumps({"ok": True, "cycles_reclaimed": 2}),  # casals_frontend destroy
        json.dumps({"ok": True}),  # convert_treasury_icp
    ]
    mock_call.side_effect = side_effects

    mock_status.side_effect = [
        CanisterStatus(canister_id=REGISTRY_ID, status="running", raw=""),
        CanisterStatus(canister_id=INSTALLER_ID, status="running", raw=""),
        CanisterStatus(canister_id="ccccc-ccccc-ccccc-ccccc-ccccc-ccc", status="running", raw=""),
        CanisterStatus(
            canister_id=CASALS_ID,
            status="running",
            raw="Balance: 100_000_000_000 cycles",
        ),
        CanisterStatus(
            canister_id=CASALS_ID,
            status="running",
            raw="Balance: 100_000_000_000 cycles",
        ),
    ]

    result = destroy_except_frontend(desc, network="ic", identity="deployer")

    assert result["ok"] is True
    assert result["preserved_frontend_ids"] == [FRONTEND_ID]
    assert result["wallet"] == WALLET_ID
    orchestra_preserve = json.loads(
        _parse_candid_string(mock_call.call_args_list[0][0][2])
    )["preserve"]
    assert orchestra_preserve == [FRONTEND_ID]
    assert mock_call.call_args_list[0][0][1] == "destroy_orchestra"
    assert mock_call.call_args_list[1][0][1] == "destroy_orchestra"
    convert_payload = json.loads(_parse_candid_string(mock_call.call_args_list[-1][0][2]))
    assert convert_payload == {}
    mock_dust_delete.assert_called_once()
    assert desc.canisters == {FRONTEND_NAME: FRONTEND_ID}
    assert desc.multisig.backend_id is None
    assert result["ephemeral_holding"] is False


@patch("gaas.destroy.dfx.delete_dust_canister")
@patch("gaas.destroy.dfx.canister_status")
@patch("gaas.destroy.dfx.get_principal")
@patch("gaas.destroy.dfx.get_wallet")
@patch("gaas.destroy.dfx.canister_call")
@patch("gaas.destroy.ensure_casals_controller")
def test_destroy_except_frontend_deletes_walletized_conductor(
    _mock_ensure: MagicMock,
    mock_call: MagicMock,
    mock_wallet: MagicMock,
    mock_principal: MagicMock,
    mock_status: MagicMock,
    mock_dust_delete: MagicMock,
    tmp_path: Path,
) -> None:
    desc = _full_descriptor(tmp_path)
    mock_wallet.return_value = WALLET_ID
    mock_principal.return_value = DEPLOYER_PRINCIPAL
    mock_call.side_effect = DfxError(
        "Canister has no update method 'destroy_orchestra'. IC0536",
        command=["dfx", "canister", "call"],
        stderr="IC0536",
    )
    mock_status.return_value = CanisterStatus(
        canister_id=CASALS_ID,
        status="running",
        raw="Balance: 531_449_609_185 cycles",
    )
    result = destroy_except_frontend(desc, network="ic", identity="deployer")
    assert result["ok"] is True
    mock_dust_delete.assert_called_once()
    assert desc.canisters == {FRONTEND_NAME: FRONTEND_ID}


@patch("gaas.destroy.dfx.delete_dust_canister")
@patch("gaas.destroy.dfx.canister_status")
@patch("gaas.destroy.dfx.get_principal")
@patch("gaas.destroy.dfx.get_wallet")
@patch("gaas.destroy.dfx.canister_call")
@patch("gaas.destroy.ensure_casals_controller")
def test_destroy_except_frontend_refuses_fat_casals(
    _mock_ensure: MagicMock,
    mock_call: MagicMock,
    mock_wallet: MagicMock,
    mock_principal: MagicMock,
    mock_status: MagicMock,
    mock_dust_delete: MagicMock,
    tmp_path: Path,
) -> None:
    desc = _full_descriptor(tmp_path)
    mock_wallet.return_value = WALLET_ID
    mock_principal.return_value = DEPLOYER_PRINCIPAL
    mock_call.side_effect = [
        json.dumps({"ok": True, "destroyed": [], "remaining": 0, "done": True, "cycles_reclaimed": 0}),
        json.dumps({"ok": True, "cycles_reclaimed": 0}),
        json.dumps({"ok": True, "cycles_reclaimed": 0}),
        json.dumps({"ok": True, "cycles_reclaimed": 0}),
        json.dumps({"ok": True}),
        json.dumps({"ok": True, "deposited": 0}),
    ]
    mock_status.side_effect = [
        CanisterStatus(canister_id=REGISTRY_ID, status="running", raw=""),
        CanisterStatus(canister_id=INSTALLER_ID, status="running", raw=""),
        CanisterStatus(canister_id="ccccc-ccccc-ccccc-ccccc-ccccc-ccc", status="running", raw=""),
        CanisterStatus(
            canister_id=CASALS_ID,
            status="running",
            raw="Balance: 20_000_000_000_000 cycles",
        ),
        CanisterStatus(
            canister_id=CASALS_ID,
            status="running",
            raw=f"Balance: {CONDUCTOR_DELETE_MAX + 1} cycles",
        ),
    ]

    with pytest.raises(RuntimeError, match="refusing delete"):
        destroy_except_frontend(desc, network="ic", identity="deployer")

    mock_dust_delete.assert_not_called()


@patch("gaas.destroy.dfx.update_canister_settings")
@patch("gaas.destroy.dfx.canister_status")
@patch("gaas.destroy.dfx.get_principal")
def test_ensure_casals_controller_adds_when_deployer_controls(
    mock_principal: MagicMock,
    mock_status: MagicMock,
    mock_update: MagicMock,
) -> None:
    mock_principal.return_value = DEPLOYER_PRINCIPAL
    mock_status.return_value = CanisterStatus(
        canister_id=REGISTRY_ID,
        status="running",
        raw="",
        controllers=(DEPLOYER_PRINCIPAL,),
    )

    ensure_casals_controller(
        REGISTRY_ID,
        casals_id=CASALS_ID,
        deployer_principal=DEPLOYER_PRINCIPAL,
        network="ic",
        identity="deployer",
    )

    mock_update.assert_called_once_with(
        REGISTRY_ID,
        [DEPLOYER_PRINCIPAL, CASALS_ID],
        "ic",
        identity="deployer",
    )


@patch("gaas.destroy.dfx.update_canister_settings")
@patch("gaas.destroy.dfx.canister_status")
def test_ensure_casals_controller_skips_missing_canister(
    mock_status: MagicMock,
    mock_update: MagicMock,
) -> None:
    mock_status.side_effect = DfxError("canister not found", command=[], stderr="IC0301")
    ensure_casals_controller(
        REGISTRY_ID,
        casals_id=CASALS_ID,
        deployer_principal=DEPLOYER_PRINCIPAL,
        network="ic",
        identity="deployer",
    )
    mock_update.assert_not_called()


def test_run_destroy_orchestra_loop_retries_invalid_controller() -> None:
    with patch("gaas.destroy._casals_call") as mock_casals, patch(
        "gaas.destroy.ensure_casals_controller"
    ) as mock_ensure:
        mock_casals.side_effect = [
            {
                "ok": True,
                "destroyed": [],
                "errors": [
                    {
                        "name": "realmstest1-backend",
                        "canister_id": "rtsxv-6aaaa-aaaab-qhe6a-cai",
                        "error": "Only the controllers of the canister can control it",
                    }
                ],
                "remaining": 3,
                "done": False,
                "cycles_reclaimed": 0,
            },
            {
                "ok": True,
                "destroyed": [{"canister_id": "rtsxv-6aaaa-aaaab-qhe6a-cai"}],
                "remaining": 0,
                "done": True,
                "cycles_reclaimed": 4,
            },
        ]
        destroyed, reclaimed = run_destroy_orchestra_loop(
            CASALS_ID,
            preserve=[FRONTEND_ID],
            network="ic",
            identity="deployer",
            deployer_principal=DEPLOYER_PRINCIPAL,
        )
    assert len(destroyed) == 1
    assert reclaimed == 4
    mock_ensure.assert_called_once()
    assert mock_casals.call_count == 2


def test_run_destroy_orchestra_loop_until_done() -> None:
    with patch("gaas.destroy._casals_call") as mock_casals:
        mock_casals.side_effect = [
            {"ok": True, "destroyed": [{"canister_id": "a"}], "remaining": 1, "done": False, "cycles_reclaimed": 1},
            {"ok": True, "destroyed": [{"canister_id": "b"}], "remaining": 0, "done": True, "cycles_reclaimed": 2},
        ]
        destroyed, reclaimed = run_destroy_orchestra_loop(
            CASALS_ID,
            preserve=[FRONTEND_ID],
            network="ic",
            identity="deployer",
        )
    assert len(destroyed) == 2
    assert reclaimed == 3
    assert mock_casals.call_count == 2


def test_run_destroy_orchestra_loop_drops_unknown_preserve() -> None:
    with patch("gaas.destroy._casals_call") as mock_casals:
        mock_casals.side_effect = [
            DfxError(
                "unknown preserve entries: h4gmt-waaaa-aaaac-bfxoq-cai",
                command=["dfx", "canister", "call"],
                stderr="unknown preserve entries",
            ),
            {"ok": True, "destroyed": [], "remaining": 0, "done": True, "cycles_reclaimed": 0},
        ]
        destroyed, reclaimed = run_destroy_orchestra_loop(
            CASALS_ID,
            preserve=[FRONTEND_ID, MARKETPLACE_FRONTEND_ID],
            network="ic",
            identity="deployer",
        )
    assert destroyed == []
    assert reclaimed == 0
    second_preserve = mock_casals.call_args_list[1][0][2]["preserve"]
    assert second_preserve == [FRONTEND_ID]


def test_run_destroy_orchestra_loop_drops_unknown_preserve_ok_false() -> None:
    with patch("gaas.destroy._casals_call") as mock_casals:
        mock_casals.side_effect = [
            {
                "ok": False,
                "error": "unknown preserve entries: mxyd5-3qaaa-aaaao-ba2xq-cai",
            },
            {"ok": True, "destroyed": [], "remaining": 0, "done": True, "cycles_reclaimed": 0},
        ]
        destroyed, reclaimed = run_destroy_orchestra_loop(
            CASALS_ID,
            preserve=[FRONTEND_ID, MARKETPLACE_FRONTEND_ID],
            network="ic",
            identity="deployer",
        )
    assert destroyed == []
    assert reclaimed == 0
    second_preserve = mock_casals.call_args_list[1][0][2]["preserve"]
    assert second_preserve == [FRONTEND_ID]


def test_evac_min_reserve_matches_conductor_delete_max() -> None:
    assert CONDUCTOR_DELETE_MAX >= EVAC_MIN_RESERVE


@patch("gaas.destroy._casals_call")
def test_also_destroy_skips_missing_canisters(mock_casals: MagicMock) -> None:
    with patch("gaas.destroy.dfx.canister_status") as mock_status:
        mock_status.side_effect = [
            DfxError("not found IC0301", command=[], stderr="IC0301"),
            CanisterStatus(canister_id=INSTALLER_ID, status="running", raw=""),
        ]
        mock_casals.return_value = {"ok": True, "cycles_reclaimed": 7}
        destroyed, reclaimed = also_destroy_descriptor_canisters(
            CASALS_ID,
            [("realm_registry_backend", REGISTRY_ID), ("realm_installer", INSTALLER_ID)],
            network="ic",
            identity="deployer",
        )
    assert len(destroyed) == 1
    assert reclaimed == 7
    mock_casals.assert_called_once()


def test_clear_destroyed_descriptor_ids_keeps_frontend_only() -> None:
    desc = Descriptor.model_validate(
        {
            **SAMPLE_DESCRIPTOR,
            "canisters": {
                FRONTEND_NAME: FRONTEND_ID,
                "realm_registry_backend": REGISTRY_ID,
                "casals_backend": CASALS_ID,
            },
            "multisig": {"backend_id": REGISTRY_ID, "signers": [], "threshold": 1},
        }
    )
    clear_destroyed_descriptor_ids(
        desc,
        destroyed_ids={REGISTRY_ID, CASALS_ID},
        preserved_frontend_ids={FRONTEND_ID},
    )
    assert desc.canisters == {FRONTEND_NAME: FRONTEND_ID}
    assert desc.multisig.backend_id is None


@patch("gaas.destroy._casals_call")
@patch("gaas.destroy.dfx.canister_status")
def test_evacuate_to_wallet_not_frontend(mock_status: MagicMock, mock_casals: MagicMock) -> None:
    mock_status.return_value = CanisterStatus(
        canister_id=CASALS_ID,
        status="running",
        raw="Balance: 20_000_000_000_000 cycles",
    )
    mock_casals.side_effect = [
        {"ok": True, "deposited": 5_000_000_000_000},
        {"ok": True, "deposited": 0},
    ]
    evacuated = evacuate_treasury_to_wallet(
        CASALS_ID,
        wallet=WALLET_ID,
        network="ic",
        identity="deployer",
    )
    assert evacuated == 5_000_000_000_000
    payload = mock_casals.call_args_list[0][0][2]
    assert payload["destination"] == WALLET_ID


MARKETPLACE_FRONTEND_ID = "h4gmt-waaaa-aaaac-bfxoq-cai"


@patch("gaas.destroy.dfx.delete_dust_canister")
@patch("gaas.destroy.dfx.canister_status")
@patch("gaas.destroy.dfx.get_principal")
@patch("gaas.destroy.dfx.get_wallet")
@patch("gaas.destroy.dfx.canister_call")
@patch("gaas.destroy.ensure_casals_controller")
def test_destroy_except_frontend_preserves_marketplace_when_present(
    mock_ensure: MagicMock,
    mock_call: MagicMock,
    mock_wallet: MagicMock,
    mock_principal: MagicMock,
    mock_status: MagicMock,
    mock_dust_delete: MagicMock,
    tmp_path: Path,
) -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "casals_backend": CASALS_ID,
        FRONTEND_NAME: FRONTEND_ID,
        "marketplace_frontend": MARKETPLACE_FRONTEND_ID,
        "realm_registry_backend": REGISTRY_ID,
        "realm_installer": INSTALLER_ID,
    }
    data["multisig"] = {"backend_id": REGISTRY_ID, "signers": [], "threshold": 1}
    path = tmp_path / "env.gaas.json"
    desc = Descriptor.model_validate(data)
    desc.save(path)
    desc = Descriptor.load(path)

    mock_wallet.return_value = WALLET_ID
    mock_principal.return_value = DEPLOYER_PRINCIPAL
    mock_call.side_effect = [
        json.dumps({"ok": True, "destroyed": [], "remaining": 0, "done": True, "cycles_reclaimed": 0}),
        json.dumps({"ok": True, "cycles_reclaimed": 5}),
        json.dumps({"ok": True, "cycles_reclaimed": 3}),
        json.dumps({"ok": True}),
        json.dumps({"ok": True, "deposited": 0}),
    ]
    mock_status.side_effect = [
        CanisterStatus(canister_id=REGISTRY_ID, status="running", raw=""),
        CanisterStatus(canister_id=INSTALLER_ID, status="running", raw=""),
        CanisterStatus(
            canister_id=CASALS_ID,
            status="running",
            raw="Balance: 100_000_000_000 cycles",
        ),
        CanisterStatus(
            canister_id=CASALS_ID,
            status="running",
            raw="Balance: 100_000_000_000 cycles",
        ),
    ]

    result = destroy_except_frontend(desc, network="ic", identity="deployer")

    assert result["preserved_frontend_ids"] == [FRONTEND_ID, MARKETPLACE_FRONTEND_ID]
    orchestra_preserve = json.loads(
        _parse_candid_string(mock_call.call_args_list[0][0][2])
    )["preserve"]
    assert orchestra_preserve == [FRONTEND_ID, MARKETPLACE_FRONTEND_ID]
    assert desc.canisters == {
        FRONTEND_NAME: FRONTEND_ID,
        "marketplace_frontend": MARKETPLACE_FRONTEND_ID,
    }
    mock_dust_delete.assert_called_once()


@patch("gaas.destroy.dfx.refund_canister_to_ledger")
@patch("gaas.destroy.dfx.create_ephemeral_canister")
@patch("gaas.destroy.dfx.delete_dust_canister")
@patch("gaas.destroy.dfx.canister_status")
@patch("gaas.destroy.dfx.get_principal")
@patch("gaas.destroy.dfx.get_wallet")
@patch("gaas.destroy.dfx.canister_call")
@patch("gaas.destroy.ensure_casals_controller")
def test_destroy_except_frontend_ephemeral_holding_when_no_wallet(
    mock_ensure: MagicMock,
    mock_call: MagicMock,
    mock_wallet: MagicMock,
    mock_principal: MagicMock,
    mock_status: MagicMock,
    mock_dust_delete: MagicMock,
    mock_create_holding: MagicMock,
    mock_refund: MagicMock,
    tmp_path: Path,
) -> None:
    desc = _full_descriptor(tmp_path)
    mock_wallet.side_effect = DfxError(
        "No wallet configured",
        command=["dfx", "identity", "get-wallet"],
        stderr="No wallet configured",
    )
    mock_create_holding.return_value = WALLET_ID
    mock_principal.return_value = DEPLOYER_PRINCIPAL
    mock_call.side_effect = [
        json.dumps({"ok": True, "destroyed": [], "remaining": 0, "done": True, "cycles_reclaimed": 0}),
        json.dumps({"ok": True, "cycles_reclaimed": 0}),
        json.dumps({"ok": True, "cycles_reclaimed": 0}),
        json.dumps({"ok": True, "cycles_reclaimed": 0}),
        json.dumps({"ok": True}),
    ]
    mock_status.side_effect = [
        CanisterStatus(canister_id=REGISTRY_ID, status="running", raw=""),
        CanisterStatus(canister_id=INSTALLER_ID, status="running", raw=""),
        CanisterStatus(canister_id="ccccc-ccccc-ccccc-ccccc-ccccc-ccc", status="running", raw=""),
        CanisterStatus(
            canister_id=CASALS_ID,
            status="running",
            raw="Balance: 100_000_000_000 cycles",
        ),
        CanisterStatus(
            canister_id=CASALS_ID,
            status="running",
            raw="Balance: 100_000_000_000 cycles",
        ),
    ]

    result = destroy_except_frontend(desc, network="ic", identity="deployer")

    assert result["ok"] is True
    assert result["wallet"] == WALLET_ID
    assert result["ephemeral_holding"] is True
    mock_create_holding.assert_called_once_with("ic", identity="deployer")
    mock_dust_delete.assert_called_once()
    mock_refund.assert_called_once_with(WALLET_ID, "ic", identity="deployer")


@patch("gaas.destroy.dfx.refund_canister_to_ledger")
@patch("gaas.destroy.dfx.create_ephemeral_canister")
@patch("gaas.destroy.dfx.delete_dust_canister")
@patch("gaas.destroy.dfx.canister_status")
@patch("gaas.destroy.dfx.get_principal")
@patch("gaas.destroy.dfx.get_wallet")
@patch("gaas.destroy.dfx.canister_call")
@patch("gaas.destroy.ensure_casals_controller")
def test_destroy_except_frontend_reuses_gaas_cycles_holding(
    mock_ensure: MagicMock,
    mock_call: MagicMock,
    mock_wallet: MagicMock,
    mock_principal: MagicMock,
    mock_status: MagicMock,
    mock_dust_delete: MagicMock,
    mock_create_holding: MagicMock,
    mock_refund: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    desc = _full_descriptor(tmp_path)
    leftover = "pd2xr-bqaaa-aaaad-agxrq-cai"
    monkeypatch.setenv(HOLDING_ENV, leftover)
    mock_wallet.side_effect = DfxError(
        "No wallet configured",
        command=["dfx", "identity", "get-wallet"],
        stderr="No wallet configured",
    )
    mock_principal.return_value = DEPLOYER_PRINCIPAL
    mock_call.side_effect = [
        json.dumps({"ok": True, "destroyed": [], "remaining": 0, "done": True, "cycles_reclaimed": 0}),
        json.dumps({"ok": True, "cycles_reclaimed": 0}),
        json.dumps({"ok": True, "cycles_reclaimed": 0}),
        json.dumps({"ok": True, "cycles_reclaimed": 0}),
        json.dumps({"ok": True}),
    ]
    mock_status.side_effect = [
        CanisterStatus(canister_id=REGISTRY_ID, status="running", raw=""),
        CanisterStatus(canister_id=INSTALLER_ID, status="running", raw=""),
        CanisterStatus(canister_id="ccccc-ccccc-ccccc-ccccc-ccccc-ccc", status="running", raw=""),
        CanisterStatus(
            canister_id=CASALS_ID,
            status="running",
            raw="Balance: 100_000_000_000 cycles",
        ),
        CanisterStatus(
            canister_id=CASALS_ID,
            status="running",
            raw="Balance: 100_000_000_000 cycles",
        ),
    ]

    result = destroy_except_frontend(desc, network="ic", identity="deployer")

    assert result["ok"] is True
    assert result["wallet"] == leftover
    assert result["ephemeral_holding"] is True
    mock_create_holding.assert_not_called()
    mock_refund.assert_called_once_with(leftover, "ic", identity="deployer")


@patch("gaas.destroy.dfx.top_up_canister")
@patch("gaas.destroy.dfx.canister_call")
def test_casals_call_tops_up_once_on_ic0207(
    mock_call: MagicMock,
    mock_top_up: MagicMock,
) -> None:
    from gaas.destroy import _casals_call

    mock_call.side_effect = [
        DfxError(
            "out of cycles IC0207",
            command=["dfx", "canister", "call"],
            stderr='Canister jo3cj-faaaa-aaaac-bffea-cai is out of cycles: error code Some("IC0207")',
        ),
        json.dumps({"ok": True, "destroyed": [], "remaining": 0, "done": True}),
    ]

    parsed = _casals_call(
        CASALS_ID,
        "destroy_orchestra",
        {"preserve": [FRONTEND_ID], "limit": 1},
        network="ic",
        identity="deployer",
    )

    assert parsed["ok"] is True
    mock_top_up.assert_called_once_with(
        CASALS_ID, CASALS_DESTROY_TOPUP, "ic", identity="deployer"
    )
    assert mock_call.call_count == 2


def test_clear_destroyed_descriptor_ids_keeps_both_dns_frontends() -> None:
    desc = Descriptor.model_validate(
        {
            **SAMPLE_DESCRIPTOR,
            "canisters": {
                FRONTEND_NAME: FRONTEND_ID,
                "marketplace_frontend": MARKETPLACE_FRONTEND_ID,
                "realm_registry_backend": REGISTRY_ID,
                "casals_backend": CASALS_ID,
            },
            "multisig": {"backend_id": REGISTRY_ID, "signers": [], "threshold": 1},
        }
    )
    clear_destroyed_descriptor_ids(
        desc,
        destroyed_ids={REGISTRY_ID, CASALS_ID},
        preserved_frontend_ids={FRONTEND_ID, MARKETPLACE_FRONTEND_ID},
    )
    assert desc.canisters == {
        FRONTEND_NAME: FRONTEND_ID,
        "marketplace_frontend": MARKETPLACE_FRONTEND_ID,
    }
    assert desc.multisig.backend_id is None


@patch("gaas.main.run_phases")
def test_new_cli_passes_destroy_except_frontend_flag(mock_run: MagicMock, tmp_path: Path) -> None:
    path = _destroy_descriptor(
        tmp_path,
        canisters={
            "casals_backend": CASALS_ID,
            FRONTEND_NAME: FRONTEND_ID,
        },
    )
    mock_run.return_value = MagicMock(completed_phases=[], preflight=None, stopped=False)

    result = runner.invoke(
        app,
        [
            "new",
            str(path),
            "--identity",
            "deployer",
            "--network",
            "ic",
            "--yes",
            "--destroy-except-realm-registry-frontend",
        ],
    )

    assert result.exit_code == 0, result.output
    ctx = mock_run.call_args[0][1]
    assert ctx.destroy_except_frontend is True
