"""Fail-closed installer liveness checks."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from gaas.canister_liveness import (
    CanisterNotFoundError,
    assert_canister_exists,
    assert_installer_live_for_network,
    main,
)
from gaas.descriptor import Descriptor
from gaas.phases import DeployContext, phase_create_canisters
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID

LIVE_INSTALLER = "ta6df-miaaa-aaaan-q6n4a-cai"
GHOST_INSTALLER = "fksuf-niaaa-aaaae-ag22q-cai"


def _live_fetch(canister_id: str):
    return 200, {"canister_id": canister_id, "module_hash": "abc"}


def _missing_fetch(_canister_id: str):
    return 404, {"code": 404, "status": "Not Found"}


def test_assert_canister_exists_accepts_live_principal():
    assert_canister_exists(LIVE_INSTALLER, role="realm_installer", fetch=_live_fetch)


def test_assert_canister_exists_rejects_http_404():
    with pytest.raises(CanisterNotFoundError, match="IC0301"):
        assert_canister_exists(GHOST_INSTALLER, role="realm_installer", fetch=_missing_fetch)


def test_assert_canister_exists_rejects_empty_id():
    with pytest.raises(CanisterNotFoundError, match="missing canister id"):
        assert_canister_exists("  ", role="realm_installer", fetch=_live_fetch)


def test_assert_canister_exists_rejects_ic0301_payload():
    def fetch(_canister_id: str):
        return 200, {"error": "IC0301 canister not found"}

    with pytest.raises(CanisterNotFoundError, match="IC0301"):
        assert_canister_exists(GHOST_INSTALLER, fetch=fetch)


def test_assert_installer_live_skips_local_network():
    assert_installer_live_for_network("", "local", fetch=lambda _id: (_ for _ in ()).throw(AssertionError("fetch")))


def test_main_exits_nonzero_for_ghost(monkeypatch):
    monkeypatch.setattr(
        "gaas.canister_liveness.fetch_canister_record",
        _missing_fetch,
    )
    assert main([GHOST_INSTALLER, "realm_installer"]) == 1


def test_canister_ids_and_dfx_point_staging_installer_at_ta6df():
    root = Path(__file__).resolve().parents[2]
    ids = json.loads((root / "canister_ids.json").read_text(encoding="utf-8"))
    dfx = json.loads((root / "dfx.json").read_text(encoding="utf-8"))
    assert ids["realm_installer"]["staging"] == LIVE_INSTALLER
    assert ids["realm_installer"]["ic"] == "hznxf-fqaaa-aaaae-ag2ua-cai"
    assert (
        dfx["canisters"]["realm_installer"]["remote"]["id"]["staging"] == LIVE_INSTALLER
    )


def test_staging_json_adopts_live_stand():
    path = Path(__file__).resolve().parents[2] / "environments" / "staging.json"
    desc = Descriptor.load(path)
    assert desc.canisters["realm_installer"] == LIVE_INSTALLER
    assert desc.canisters["realm_registry_backend"] == "snqhl-daaaa-aaaan-q6n3q-cai"
    assert desc.canisters["casals_backend"] == "th7fr-bqaaa-aaaan-q6n4q-cai"
    assert desc.canisters["file_registry"] == "t42zu-3iaaa-aaaan-q6n6a-cai"
    assert desc.canisters["marketplace_backend"] == "tsyu4-ayaaa-aaaan-q6n7a-cai"
    assert desc.canisters["realm_registry_frontend"] == "77243-aqaaa-aaaau-aggza-cai"
    assert desc.canisters["marketplace_frontend"] == "h4gmt-waaaa-aaaac-bfxoq-cai"
    assert GHOST_INSTALLER not in desc.canisters.values()
    assert "hznxf-fqaaa-aaaae-ag2ua-cai" not in desc.canisters.values()


@patch("gaas.phases.dfx.create_canister_via_ledger")
@patch("gaas.phases.dfx.create_canister")
@patch("gaas.phases.dfx.canister_status")
@patch("gaas.phases.dfx.get_principal", return_value="aaaaa-aa")
@patch("gaas.phases.dfx.use_identity")
def test_adopt_rejects_ghost_staging_installer(
    _use_identity,
    _principal,
    mock_status,
    mock_create,
    _ledger,
    tmp_path: Path,
) -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["name"] = "staging"
    data["domain"] = "staging.gos.earth"
    data["canisters"] = {
        "realm_installer": GHOST_INSTALLER,
    }
    desc = Descriptor.model_validate(data)
    path = tmp_path / "staging.json"
    desc.save(path)
    ctx = DeployContext(identity="deployer", network="ic", descriptor_path=path)

    with patch("gaas.phases.assert_installer_live_for_network", side_effect=CanisterNotFoundError("canister not found (IC0301)")):
        with pytest.raises(RuntimeError, match="IC0301"):
            phase_create_canisters(desc, ctx)

    mock_status.assert_not_called()
    mock_create.assert_not_called()


@patch("gaas.phases.assert_installer_live_for_network")
@patch("gaas.phases.dfx.create_canister_via_ledger")
@patch("gaas.phases.dfx.create_canister")
@patch("gaas.phases.dfx.canister_status")
@patch("gaas.phases.dfx.get_principal", return_value="aaaaa-aa")
@patch("gaas.phases.dfx.use_identity")
def test_adopt_allows_live_staging_installer(
    _use_identity,
    _principal,
    mock_status,
    mock_create,
    _ledger,
    mock_live,
    tmp_path: Path,
) -> None:
    from unittest.mock import MagicMock

    mock_status.return_value = MagicMock(
        status="running",
        controllers=("aaaaa-aa",),
        raw="status: running",
    )
    mock_create.side_effect = [
        "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
        "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
        "ccccc-ccccc-ccccc-ccccc-ccccc-ccc",
        "ddddd-ddddd-ddddd-ddddd-ddddd-ddd",
        "eeeee-eeeee-eeeee-eeeee-eeeee-eee",
        "fffff-fffff-fffff-fffff-fffff-fff",
        "ggggg-ggggg-ggggg-ggggg-ggggg-ggg",
    ]
    data = dict(SAMPLE_DESCRIPTOR)
    data["name"] = "staging"
    data["domain"] = "staging.gos.earth"
    data["canisters"] = {
        "realm_registry_backend": VALID_CANISTER_ID,
        "realm_installer": LIVE_INSTALLER,
    }
    desc = Descriptor.model_validate(data)
    path = tmp_path / "staging.json"
    desc.save(path)
    ctx = DeployContext(identity="deployer", network="ic", descriptor_path=path)

    phase_create_canisters(desc, ctx)

    mock_live.assert_called_once_with(LIVE_INSTALLER, "staging")
    assert desc.canisters["realm_installer"] == LIVE_INSTALLER
