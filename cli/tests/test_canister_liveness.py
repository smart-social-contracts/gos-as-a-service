"""Fail-closed installer liveness checks."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from gaas.canister_liveness import (
    CanisterNotFoundError,
    assert_canister_exists,
    assert_casals_frontend_live,
    assert_frontend_http_live,
    assert_installer_live_for_network,
    collect_baked_portal_frontends,
    fetch_local_canister_record,
    is_known_dead_canister,
    main,
    probe_baked_portal_frontends,
)
from gaas.descriptor import Descriptor
from gaas.phases import DeployContext, phase_create_canisters
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID

LIVE_INSTALLER = "ta6df-miaaa-aaaan-q6n4a-cai"
GHOST_INSTALLER = "fksuf-niaaa-aaaae-ag22q-cai"
LIVE_CASALS_FRONTEND = "to4on-xyaaa-aaaan-q6n5a-cai"
LIVE_TEST_CASALS_FRONTEND = "qic2k-baaaa-aaaae-agvga-cai"
DEAD_CASALS_FRONTEND = "fdr7z-3aaaa-aaaae-ag23a-cai"


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


def test_assert_installer_live_skips_empty_id_on_local():
    assert_installer_live_for_network(
        "", "local", fetch=lambda _id: (_ for _ in ()).throw(AssertionError("fetch"))
    )


def test_assert_installer_live_rejects_ghost_on_local():
    with pytest.raises(CanisterNotFoundError, match="IC0301"):
        assert_installer_live_for_network(GHOST_INSTALLER, "local", fetch=_missing_fetch)


def test_assert_installer_live_accepts_live_local_principal():
    assert_installer_live_for_network(LIVE_INSTALLER, "local", fetch=_live_fetch)


def test_assert_installer_live_local_does_not_call_ic_api(monkeypatch):
    calls: list[str] = []

    def local_fetch(canister_id: str):
        calls.append(canister_id)
        return 200, {"canister_id": canister_id}

    monkeypatch.setattr("gaas.canister_liveness.fetch_local_canister_record", local_fetch)
    monkeypatch.setattr(
        "gaas.canister_liveness.fetch_canister_record",
        lambda _id: (_ for _ in ()).throw(AssertionError("ic api")),
    )
    assert_installer_live_for_network(LIVE_INSTALLER, "local")
    assert calls == [LIVE_INSTALLER]


def test_fetch_local_canister_record_maps_missing_to_ic0301():
    from gaas.dfx import DfxError

    def _missing(*_args, **_kwargs):
        raise DfxError("canister not found", command=[], stderr="IC0301")

    with patch("gaas.dfx.canister_status", side_effect=_missing):
        status, payload = fetch_local_canister_record(GHOST_INSTALLER)
    assert status == 404
    assert "IC0301" in json.dumps(payload)


def test_fetch_local_canister_record_maps_running_status():
    from unittest.mock import MagicMock

    with patch(
        "gaas.dfx.canister_status",
        return_value=MagicMock(status="running"),
    ):
        status, payload = fetch_local_canister_record(LIVE_INSTALLER)
    assert status == 200
    assert payload["canister_id"] == LIVE_INSTALLER
    assert payload["status"] == "running"


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
    assert ids["casals_frontend"]["staging"] == LIVE_CASALS_FRONTEND
    assert ids["casals_frontend"]["test"] == LIVE_TEST_CASALS_FRONTEND
    assert DEAD_CASALS_FRONTEND not in json.dumps(ids)
    assert DEAD_CASALS_FRONTEND not in json.dumps(dfx)
    assert "fdr7z" not in json.dumps(ids)
    assert dfx["canisters"]["casals_frontend"]["remote"]["id"]["staging"] == (
        LIVE_CASALS_FRONTEND
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
    assert desc.canisters["casals_frontend"] == LIVE_CASALS_FRONTEND
    assert GHOST_INSTALLER not in desc.canisters.values()
    assert "hznxf-fqaaa-aaaae-ag2ua-cai" not in desc.canisters.values()
    assert DEAD_CASALS_FRONTEND not in desc.canisters.values()


@patch("gaas.phases.dfx.create_canister_via_ledger")
@patch("gaas.phases.dfx.create_canister")
@patch("gaas.phases.dfx.canister_status")
@patch("gaas.phases.dfx.get_principal", return_value="aaaaa-aa")
@patch("gaas.phases.dfx.use_identity")
@patch("gaas.phases._persist_and_guard_portal_frontends")
def test_adopt_rejects_ghost_staging_installer(
    _persist,
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
@patch("gaas.phases._persist_and_guard_portal_frontends")
def test_adopt_allows_live_staging_installer(
    _persist,
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

    mock_live.assert_called_once_with(LIVE_INSTALLER, "ic")
    assert desc.canisters["realm_installer"] == LIVE_INSTALLER


def test_known_dead_prefixes_include_fdr7z():
    assert is_known_dead_canister(DEAD_CASALS_FRONTEND)
    assert is_known_dead_canister("h6mrr-iiaaa-aaaae-ag2uq-cai")
    assert not is_known_dead_canister(LIVE_CASALS_FRONTEND)


def test_assert_frontend_http_live_rejects_404():
    def http_get(_canister_id: str):
        return 404, '{"error_type":"canister_not_found"}'

    with pytest.raises(CanisterNotFoundError, match="IC0301"):
        assert_frontend_http_live(LIVE_CASALS_FRONTEND, http_get=http_get)


def test_assert_frontend_http_live_rejects_known_dead_without_network():
    with pytest.raises(CanisterNotFoundError, match="known-dead"):
        assert_frontend_http_live(
            DEAD_CASALS_FRONTEND,
            http_get=lambda _id: (_ for _ in ()).throw(AssertionError("must not fetch")),
        )


def test_assert_frontend_http_live_accepts_200():
    def http_get(_canister_id: str):
        return 200, "<!doctype html><html><title>Casals</title></html>"

    assert_frontend_http_live(LIVE_CASALS_FRONTEND, http_get=http_get)


def test_assert_casals_frontend_live_allows_empty_id():
    assert_casals_frontend_live(
        "",
        "staging",
        http_get=lambda _id: (_ for _ in ()).throw(AssertionError("must not fetch")),
    )


def test_assert_casals_frontend_live_skips_local():
    assert_casals_frontend_live(
        DEAD_CASALS_FRONTEND,
        "local",
        http_get=lambda _id: (_ for _ in ()).throw(AssertionError("must not fetch")),
    )


def test_assert_casals_frontend_live_http_required_rejects_404():
    with pytest.raises(CanisterNotFoundError, match="IC0301"):
        assert_casals_frontend_live(
            LIVE_CASALS_FRONTEND,
            "staging",
            http_get=lambda _id: (404, "canister not found"),
            require_http=True,
        )


def test_probe_baked_rejects_dead_casals_frontend(tmp_path: Path):
    (tmp_path / "canister_ids.json").write_text(
        json.dumps(
            {
                "casals_frontend": {
                    "staging": DEAD_CASALS_FRONTEND,
                    "test": LIVE_TEST_CASALS_FRONTEND,
                }
            }
        ),
        encoding="utf-8",
    )
    env_dir = tmp_path / "environments"
    env_dir.mkdir()
    (env_dir / "test.json").write_text(
        json.dumps({"name": "test", "canisters": {"casals_frontend": LIVE_TEST_CASALS_FRONTEND}}),
        encoding="utf-8",
    )

    def http_get(canister_id: str):
        if canister_id == DEAD_CASALS_FRONTEND:
            return 404, '{"error_type":"canister_not_found"}'
        return 200, "<html>ok</html>"

    with pytest.raises(CanisterNotFoundError, match="known-dead"):
        probe_baked_portal_frontends(tmp_path, http_get=http_get)


def test_probe_baked_accepts_live_frontends(tmp_path: Path):
    (tmp_path / "canister_ids.json").write_text(
        json.dumps({"casals_frontend": {"test": LIVE_TEST_CASALS_FRONTEND}}),
        encoding="utf-8",
    )
    probe_baked_portal_frontends(
        tmp_path,
        http_get=lambda _id: (200, "<html>ok</html>"),
    )
    collected = collect_baked_portal_frontends(tmp_path)
    assert collected[0][3] == LIVE_TEST_CASALS_FRONTEND


def test_main_probe_baked_exits_nonzero_for_ghost(tmp_path: Path, monkeypatch):
    (tmp_path / "canister_ids.json").write_text(
        json.dumps({"casals_frontend": {"staging": DEAD_CASALS_FRONTEND}}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert main(["--probe-baked", str(tmp_path)]) == 1


@patch("gaas.phases.persist_descriptor_canister_ids")
@patch("gaas.phases.assert_casals_frontend_live", side_effect=CanisterNotFoundError("canister not found (IC0301)"))
def test_persist_guard_fails_gaas_new_on_dead_casals_frontend(mock_live, _persist):
    from gaas.phases import DeployContext, _persist_and_guard_portal_frontends

    data = dict(SAMPLE_DESCRIPTOR)
    data["name"] = "staging"
    data["domain"] = "staging.gos.earth"
    data["canisters"] = {"casals_frontend": DEAD_CASALS_FRONTEND}
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic")
    with pytest.raises(RuntimeError, match="IC0301"):
        _persist_and_guard_portal_frontends(desc, ctx, require_http=True)
    mock_live.assert_called_once()
    _persist.assert_not_called()


@patch("gaas.phases.dfx.create_canister_via_ledger")
@patch("gaas.phases.dfx.create_canister")
@patch("gaas.phases.dfx.canister_status")
@patch("gaas.phases.dfx.get_principal", return_value="aaaaa-aa")
@patch("gaas.phases.dfx.use_identity")
@patch("gaas.phases._persist_and_guard_portal_frontends")
def test_adopt_rejects_ghost_local_installer(
    _persist,
    _use_identity,
    _principal,
    mock_status,
    mock_create,
    _ledger,
    tmp_path: Path,
) -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["name"] = "local"
    data["domain"] = "local.localhost"
    data["canisters"] = {
        "realm_installer": GHOST_INSTALLER,
        "realm_registry_backend": VALID_CANISTER_ID,
    }
    desc = Descriptor.model_validate(data)
    path = tmp_path / "local.json"
    desc.save(path)
    ctx = DeployContext(identity="default", network="local", descriptor_path=path)

    with patch(
        "gaas.phases.assert_installer_live_for_network",
        side_effect=CanisterNotFoundError("canister not found (IC0301)"),
    ):
        with pytest.raises(RuntimeError, match="IC0301"):
            phase_create_canisters(desc, ctx)

    mock_status.assert_not_called()
    mock_create.assert_not_called()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["canisters"]["realm_installer"] == GHOST_INSTALLER
    assert saved["canisters"]["realm_registry_backend"] == VALID_CANISTER_ID


@patch("gaas.canister_liveness.fetch_local_canister_record", side_effect=_missing_fetch)
@patch("gaas.phases.dfx.create_canister_via_ledger")
@patch("gaas.phases.dfx.create_canister")
@patch("gaas.phases.dfx.canister_status")
@patch("gaas.phases.dfx.get_principal", return_value="aaaaa-aa")
@patch("gaas.phases.dfx.use_identity")
@patch("gaas.phases._persist_and_guard_portal_frontends")
def test_adopt_rejects_ghost_local_installer_via_replica_ping(
    _persist,
    _use_identity,
    _principal,
    mock_status,
    mock_create,
    _ledger,
    _local_fetch,
    tmp_path: Path,
) -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["name"] = "local"
    data["domain"] = "local.localhost"
    data["canisters"] = {"realm_installer": GHOST_INSTALLER}
    desc = Descriptor.model_validate(data)
    path = tmp_path / "local-ghost.json"
    desc.save(path)
    ctx = DeployContext(identity="default", network="local", descriptor_path=path)

    with pytest.raises(RuntimeError, match="IC0301"):
        phase_create_canisters(desc, ctx)

    mock_status.assert_not_called()
    mock_create.assert_not_called()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["canisters"]["realm_installer"] == GHOST_INSTALLER

