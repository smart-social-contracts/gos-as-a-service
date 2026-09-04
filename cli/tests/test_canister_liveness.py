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
    fetch_canister_record,
    fetch_local_canister_record,
    is_known_dead_canister,
    main,
    probe_baked_portal_frontends,
)
from gaas.descriptor import Descriptor
from gaas.phases import DeployContext, phase_create_canisters
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID, mock_run_casals_new

LIVE_INSTALLER = "ta6df-miaaa-aaaan-q6n4a-cai"
GHOST_INSTALLER = "fksuf-niaaa-aaaae-ag22q-cai"
LIVE_CASALS_FRONTEND = "to4on-xyaaa-aaaan-q6n5a-cai"
LIVE_TEST_CASALS_FRONTEND = "3jajj-hyaaa-aaaad-qmdda-cai"
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


def test_fetch_local_canister_record_maps_generic_dfx_error_to_ic0301():
    from gaas.dfx import DfxError

    def _missing(*_args, **_kwargs):
        raise DfxError("Http Error: status 400 Bad Request", command=[], stderr="")

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


def test_fetch_canister_record_falls_back_to_replica_when_api_404():
    from unittest.mock import MagicMock

    with patch(
        "gaas.canister_liveness.fetch_canister_record_from_api",
        return_value=(404, {"code": 404, "status": "Not Found"}),
    ), patch(
        "gaas.dfx.canister_status",
        return_value=MagicMock(status="running"),
    ):
        status, payload = fetch_canister_record(LIVE_CASALS_FRONTEND)
    assert status == 200
    assert payload["canister_id"] == LIVE_CASALS_FRONTEND
    assert payload["status"] == "running"


def test_fetch_canister_record_keeps_api_404_when_replica_also_missing():
    from gaas.dfx import DfxError

    def _missing(*_args, **_kwargs):
        raise DfxError("canister not found", command=[], stderr="IC0301")

    api_payload = {"code": 404, "status": "Not Found"}
    with patch(
        "gaas.canister_liveness.fetch_canister_record_from_api",
        return_value=(404, api_payload),
    ), patch("gaas.dfx.canister_status", side_effect=_missing):
        status, payload = fetch_canister_record(GHOST_INSTALLER)
    assert status == 404
    assert payload == api_payload


def test_assert_canister_exists_accepts_replica_fallback_after_api_404():
    from unittest.mock import MagicMock

    with patch(
        "gaas.canister_liveness.fetch_canister_record_from_api",
        return_value=(404, {"code": 404, "status": "Not Found"}),
    ), patch(
        "gaas.dfx.canister_status",
        return_value=MagicMock(status="running"),
    ):
        assert_canister_exists(LIVE_CASALS_FRONTEND, role="casals_frontend")


def test_main_exits_nonzero_for_ghost(monkeypatch):
    monkeypatch.setattr(
        "gaas.canister_liveness.fetch_canister_record",
        _missing_fetch,
    )
    assert main([GHOST_INSTALLER, "realm_installer"]) == 1


def test_canister_ids_and_dfx_carry_no_dead_ids():
    """Inventory files hold no id we know to be gone.

    Ids themselves are not pinned: a deploy legitimately rewrites them, and a
    test that hardcodes them just goes stale and gets ignored.
    """
    root = Path(__file__).resolve().parents[2]
    ids = json.loads((root / "canister_ids.json").read_text(encoding="utf-8"))
    dfx = json.loads((root / "dfx.json").read_text(encoding="utf-8"))
    for blob in (json.dumps(ids), json.dumps(dfx)):
        for dead in ("hznxf", "gudtl", "fdr7z", DEAD_CASALS_FRONTEND):
            assert dead not in blob
    for name, entry in ids.items():
        if not isinstance(entry, dict):
            continue
        for env, canister_id in entry.items():
            assert not is_known_dead_canister(canister_id), f"{name}.{env}"


def test_canister_ids_never_share_one_canister_between_environments():
    """The shared "ic" row let staging adopt test's registry and installer."""
    root = Path(__file__).resolve().parents[2]
    ids = json.loads((root / "canister_ids.json").read_text(encoding="utf-8"))
    for name, entry in ids.items():
        if not isinstance(entry, dict):
            continue
        by_env = {
            env: cid for env, cid in entry.items() if env != "ic" and (cid or "").strip()
        }
        duplicates = {
            cid for cid in by_env.values() if list(by_env.values()).count(cid) > 1
        }
        assert not duplicates, f"{name}: same canister in several environments: {duplicates}"


def test_dfx_remote_ids_agree_with_canister_ids():
    root = Path(__file__).resolve().parents[2]
    ids = json.loads((root / "canister_ids.json").read_text(encoding="utf-8"))
    dfx = json.loads((root / "dfx.json").read_text(encoding="utf-8"))
    for dfx_name, spec in (dfx.get("canisters") or {}).items():
        remote = (spec or {}).get("remote")
        if not isinstance(remote, dict):
            continue
        for env, canister_id in (remote.get("id") or {}).items():
            known = (ids.get(dfx_name) or {}).get(env)
            if known:
                assert canister_id == known, f"{dfx_name}.{env}"


def _environment_descriptors() -> dict[str, Descriptor]:
    env_dir = Path(__file__).resolve().parents[2] / "environments"
    return {
        name: Descriptor.load(env_dir / f"{name}.json")
        for name in ("test", "staging", "demo")
    }


def test_staging_json_holds_no_dead_or_product_canisters():
    """Structure only — a real deploy rewrites these ids, so none are pinned here.

    Realms GOS product canisters (file_registry, marketplace_*) belong to
    `realms seed`, not to a GaaS descriptor.
    """
    desc = _environment_descriptors()["staging"]
    assert "file_registry" not in desc.canisters
    assert "marketplace_backend" not in desc.canisters
    assert "marketplace_frontend" not in desc.canisters
    assert GHOST_INSTALLER not in desc.canisters.values()
    assert "hznxf-fqaaa-aaaae-ag2ua-cai" not in desc.canisters.values()
    assert DEAD_CASALS_FRONTEND not in desc.canisters.values()


def test_environments_never_share_a_canister():
    """No two environments may name the same canister.

    They all deploy with --network ic, and dfx keys canister_ids.json by network,
    so a shared "ic" row once made staging's `dfx canister create` hand back
    test's live registry and installer — which the staging run then upgraded and
    reconfigured as staging, taking test.gos.earth down with it.
    """
    descriptors = _environment_descriptors()
    owners: dict[str, str] = {}
    shared: dict[str, list[str]] = {}
    for env, desc in descriptors.items():
        for name, canister_id in desc.canisters.items():
            cid = (canister_id or "").strip()
            if not cid:
                continue
            if cid in owners:
                shared.setdefault(cid, [owners[cid]]).append(f"{env}.{name}")
            else:
                owners[cid] = f"{env}.{name}"
    assert not shared, f"canisters claimed by more than one environment: {shared}"


@patch("gaas.phases.run_casals_new", side_effect=mock_run_casals_new)
@patch("gaas.phases.dfx.create_canister_via_ledger")
@patch("gaas.phases.dfx.create_canister")
@patch("gaas.phases.dfx.canister_status")
@patch("gaas.phases.dfx.get_principal", return_value="aaaaa-aa")
@patch("gaas.phases.dfx.use_identity")
@patch("gaas.phases._persist_and_guard_portal_frontends")
def test_adopt_heals_ghost_staging_installer(
    _persist,
    _use_identity,
    _principal,
    mock_status,
    mock_create,
    _ledger,
    _mock_casals_new,
    tmp_path: Path,
) -> None:
    from gaas.dfx import DfxError
    from unittest.mock import MagicMock

    dead = GHOST_INSTALLER
    minted = "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb"

    def fake_status(cid, network, **kwargs):
        if cid == dead:
            raise DfxError(
                "Canister not found",
                command=["dfx", "canister", "status", cid],
                stderr="IC0301",
            )
        return MagicMock(
            status="running",
            controllers=("aaaaa-aa",),
            raw="status: running",
        )

    mock_status.side_effect = fake_status
    mock_create.side_effect = [
        "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
        minted,
    ]

    data = dict(SAMPLE_DESCRIPTOR)
    data["name"] = "staging"
    data["domain"] = "staging.gos.earth"
    data["canisters"] = {
        "realm_registry_backend": VALID_CANISTER_ID,
        "realm_installer": dead,
    }
    desc = Descriptor.model_validate(data)
    path = tmp_path / "staging.json"
    desc.save(path)
    ctx = DeployContext(identity="deployer", network="ic", descriptor_path=path)

    phase_create_canisters(desc, ctx)

    assert desc.canisters["realm_installer"] == minted
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["canisters"]["realm_installer"] == minted


@patch("gaas.phases.run_casals_new", side_effect=mock_run_casals_new)
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
    _mock_casals_new,
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
    assert is_known_dead_canister("ulsvn-pyaaa-aaaae-qj4tq-cai")
    assert is_known_dead_canister("hvwpv-aiaaa-aaaam-ajddq-cai")
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


@patch("gaas.phases.run_casals_new", side_effect=mock_run_casals_new)
@patch("gaas.phases.dfx.create_canister_via_ledger")
@patch("gaas.phases.dfx.create_canister")
@patch("gaas.phases.dfx.canister_status")
@patch("gaas.phases.dfx.get_principal", return_value="aaaaa-aa")
@patch("gaas.phases.dfx.use_identity")
@patch("gaas.phases._persist_and_guard_portal_frontends")
def test_adopt_heals_ghost_local_installer(
    _persist,
    _use_identity,
    _principal,
    mock_status,
    mock_create,
    _ledger,
    _mock_casals_new,
    tmp_path: Path,
) -> None:
    from gaas.dfx import DfxError
    from unittest.mock import MagicMock

    dead = GHOST_INSTALLER
    minted = "ccccc-ccccc-ccccc-ccccc-ccc"

    def fake_status(cid, network, **kwargs):
        if cid == dead:
            raise DfxError(
                "Canister not found",
                command=["dfx", "canister", "status", cid],
                stderr="IC0301",
            )
        return MagicMock(
            status="running",
            controllers=("aaaaa-aa",),
            raw="status: running",
        )

    mock_status.side_effect = fake_status
    # Keyed on which canister is created rather than call order: how many
    # canisters are created before the installer is an implementation detail.
    def fake_create(dfx_name, network, **kwargs):
        if "installer" in dfx_name:
            return minted
        return "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa"

    mock_create.side_effect = fake_create

    data = dict(SAMPLE_DESCRIPTOR)
    data["name"] = "local"
    data["domain"] = "local.localhost"
    data["canisters"] = {
        "realm_installer": dead,
        "realm_registry_backend": VALID_CANISTER_ID,
    }
    desc = Descriptor.model_validate(data)
    path = tmp_path / "local.json"
    desc.save(path)
    ctx = DeployContext(identity="default", network="local", descriptor_path=path)

    phase_create_canisters(desc, ctx)

    assert desc.canisters["realm_installer"] == minted
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["canisters"]["realm_installer"] == minted


@patch("gaas.phases.run_casals_new", side_effect=mock_run_casals_new)
@patch("gaas.phases.dfx.create_canister_via_ledger")
@patch("gaas.phases.dfx.create_canister")
@patch("gaas.phases.dfx.canister_status")
@patch("gaas.phases.dfx.get_principal", return_value="aaaaa-aa")
@patch("gaas.phases.dfx.use_identity")
@patch("gaas.phases._persist_and_guard_portal_frontends")
def test_adopt_heals_ghost_local_installer_via_replica_ping(
    _persist,
    _use_identity,
    _principal,
    mock_status,
    mock_create,
    _ledger,
    _mock_casals_new,
    tmp_path: Path,
) -> None:
    from gaas.dfx import DfxError
    from unittest.mock import MagicMock

    dead = GHOST_INSTALLER
    minted = "ccccc-ccccc-ccccc-ccccc-ccc"

    def fake_status(cid, network, **kwargs):
        if cid == dead:
            raise DfxError(
                "Canister not found",
                command=["dfx", "canister", "status", cid],
                stderr="IC0301",
            )
        return MagicMock(
            status="running",
            controllers=("aaaaa-aa",),
            raw="status: running",
        )

    mock_status.side_effect = fake_status
    # Keyed on which canister is created rather than call order: how many
    # canisters are created before the installer is an implementation detail.
    def fake_create(dfx_name, network, **kwargs):
        if "installer" in dfx_name:
            return minted
        return "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa"

    mock_create.side_effect = fake_create

    data = dict(SAMPLE_DESCRIPTOR)
    data["name"] = "local"
    data["domain"] = "local.localhost"
    data["canisters"] = {"realm_installer": dead}
    desc = Descriptor.model_validate(data)
    path = tmp_path / "local-ghost.json"
    desc.save(path)
    ctx = DeployContext(identity="default", network="local", descriptor_path=path)

    phase_create_canisters(desc, ctx)

    assert desc.canisters["realm_installer"] == minted
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["canisters"]["realm_installer"] == minted

