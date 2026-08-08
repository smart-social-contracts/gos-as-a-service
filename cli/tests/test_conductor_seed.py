"""Tests for Casals conductor seed helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from gaas import conductor_seed
from gaas.conductor_seed import platform_sheet
from gaas.descriptor import Descriptor
from gaas.platform import PlatformError, find_local_assetstorage_wasm
from tests.conftest import SAMPLE_DESCRIPTOR


def test_platform_sheet_has_infra_and_deployments() -> None:
    sheet = platform_sheet()
    names = [sec["name"] for sec in sheet["sections"]]
    assert names == ["Infra", "Deployments"]
    infra = sheet["sections"][0]
    assert infra["stands"][0]["name"] == "governance"
    assert infra["stands"][0]["canisters"][0]["name"] == "multisig"
    assert sheet["sections"][1]["stands"] == []


def test_ensure_deployments_commander_grants_installer(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        conductor_seed,
        "_casals_call",
        lambda _cid, method, payload, _net, **_: calls.append((method, payload))
        or {"ok": True},
    )
    conductor_seed.ensure_deployments_commander(
        "qthgp-3yaaa-aaaae-agveq-cai", "fltjm-tyaaa-aaaap-qunhq-cai", "ic"
    )
    assert calls == [
        (
            "set_commander",
            {
                "section": "Deployments",
                "commander_principal": "fltjm-tyaaa-aaaap-qunhq-cai",
                "permissions": conductor_seed.DEPLOYMENTS_COMMANDER_PERMISSIONS,
            },
        )
    ]
    perms = calls[0][1]["permissions"]
    for required in (
        "stand.create",
        "canister.create",
        "canister.deploy",
        "commander.assign",
        "orchestration.baton.create",
        "orchestration.baton.hand_off",
        "orchestration.managed_upgrade.run",
    ):
        assert required in perms


def _write_assetstorage_wasm(repo_root: Path, canister: str = "realm_registry_frontend") -> Path:
    wasm_dir = repo_root / ".dfx" / "ic" / "canisters" / canister
    wasm_dir.mkdir(parents=True, exist_ok=True)
    wasm_path = wasm_dir / "assetstorage.wasm.gz"
    wasm_path.write_bytes(b"\x00asm" + b"\x01" * 64)
    return wasm_path


def test_find_local_assetstorage_wasm_prefers_repo_dfx_build(tmp_path: Path) -> None:
    expected = _write_assetstorage_wasm(tmp_path)
    assert find_local_assetstorage_wasm(tmp_path) == expected


def test_find_local_assetstorage_wasm_falls_back_to_dfx_cache(
    tmp_path: Path, monkeypatch
) -> None:
    from gaas import dfx

    cache_root = tmp_path / "dfx-cache"
    cache_root.mkdir()
    cache_wasm = cache_root / "assetstorage.wasm.gz"
    cache_wasm.write_bytes(b"cache-wasm")

    monkeypatch.setattr(
        dfx,
        "_run",
        lambda *args, **kwargs: type("R", (), {"stdout": str(cache_root)})(),
    )
    assert find_local_assetstorage_wasm(None) == cache_wasm


def test_find_local_assetstorage_wasm_raises_when_missing(tmp_path: Path, monkeypatch) -> None:
    from gaas import dfx

    monkeypatch.setattr(
        dfx,
        "_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(dfx.DfxError("no cache", command=[], stderr="")),
    )
    with pytest.raises(PlatformError, match="assetstorage.wasm.gz"):
        find_local_assetstorage_wasm(tmp_path)


def test_ensure_assetstorage_wasm_uploads_and_returns_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    wasm_path = _write_assetstorage_wasm(tmp_path)
    expected_hash = hashlib.sha256(wasm_path.read_bytes()).hexdigest()
    upload_calls: list[tuple] = []

    monkeypatch.setattr(
        conductor_seed,
        "fetch_namespace_hashes",
        lambda *_a, **_k: {},
    )
    monkeypatch.setattr(
        conductor_seed,
        "upload_file",
        lambda *args, **kwargs: upload_calls.append((args, kwargs)) or "uploaded",
    )

    ns, path, digest = conductor_seed.ensure_assetstorage_wasm(
        "uq2mu-kaaaa-aaaah-avqcq-cai", "main", "ic", repo_root=tmp_path
    )
    assert ns == "wasm/realm-assetstorage/main"
    assert path == "realms-assetstorage.wasm.gz"
    assert digest == expected_hash
    assert len(upload_calls) == 1


def test_ensure_assetstorage_wasm_skips_when_hash_matches(
    tmp_path: Path, monkeypatch
) -> None:
    wasm_path = _write_assetstorage_wasm(tmp_path)
    expected_hash = hashlib.sha256(wasm_path.read_bytes()).hexdigest()
    upload_called = False

    monkeypatch.setattr(
        conductor_seed,
        "fetch_namespace_hashes",
        lambda *_a, **_k: {"realms-assetstorage.wasm.gz": expected_hash},
    )

    def _upload(*_a, **_k):
        nonlocal upload_called
        upload_called = True
        return "uploaded"

    monkeypatch.setattr(conductor_seed, "upload_file", _upload)

    ns, path, digest = conductor_seed.ensure_assetstorage_wasm(
        "uq2mu-kaaaa-aaaah-avqcq-cai", "main", "ic", repo_root=tmp_path
    )
    assert ns == "wasm/realm-assetstorage/main"
    assert path == "realms-assetstorage.wasm.gz"
    assert digest == expected_hash
    assert upload_called is False


def test_authorize_gos_entry_frontend_uses_assetstorage_wasm(
    tmp_path: Path, monkeypatch
) -> None:
    _write_assetstorage_wasm(tmp_path)
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    entry = desc.gos[0]
    casals_calls: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        conductor_seed,
        "resolve_deploy_version",
        lambda *_a, **_k: type("R", (), {"catalog_version": "0.3.1"})(),
    )
    monkeypatch.setattr(
        conductor_seed,
        "fetch_namespace_hashes",
        lambda _rid, ns, *_a, **_k: (
            {"realm_backend.wasm.gz": "abc123"}
            if ns == "wasm/realm-backend/0.3.1"
            else {}
        ),
    )
    monkeypatch.setattr(
        conductor_seed,
        "list_authorized_keys",
        lambda *_a, **_k: {},
    )
    monkeypatch.setattr(
        conductor_seed,
        "_casals_call",
        lambda _cid, method, payload, _net, **_: casals_calls.append((method, payload))
        or {"ok": True},
    )
    monkeypatch.setattr(conductor_seed, "upload_file", lambda *_a, **_k: "uploaded")

    conductor_seed.authorize_gos_entry(
        "qthgp-3yaaa-aaaae-agveq-cai",
        "uq2mu-kaaaa-aaaah-avqcq-cai",
        desc,
        entry,
        "ic",
        repo_root=tmp_path,
    )

    frontend_calls = [
        payload for method, payload in casals_calls if method == "add_authorized_wasm" and payload.get("kind") == "frontend"
    ]
    assert len(frontend_calls) == 1
    payload = frontend_calls[0]
    assert payload["key"] == "realm-assets"
    assert payload["version"] == "0.3.1"
    assert payload["registry_namespace"] == "wasm/realm-assetstorage/0.3.1"
    assert payload["registry_path"] == "realms-assetstorage.wasm.gz"
    assert payload["kind"] == "frontend"
    assert "certified-assets wasm" in payload["description"]
    assert "bundle_namespace" not in payload


def test_authorize_gos_entry_frontend_works_without_bundle_namespace(
    tmp_path: Path, monkeypatch
) -> None:
    """Empty frontend bundle namespace must not block frontend wasm authorization."""
    _write_assetstorage_wasm(tmp_path)
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    entry = desc.gos[0]
    casals_calls: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        conductor_seed,
        "resolve_deploy_version",
        lambda *_a, **_k: type("R", (), {"catalog_version": "main"})(),
    )
    monkeypatch.setattr(
        conductor_seed,
        "fetch_namespace_hashes",
        lambda _rid, ns, *_a, **_k: (
            {"realm_backend.wasm.gz": "backendhash"}
            if ns == "wasm/realm-backend/main"
            else {}
        ),
    )
    monkeypatch.setattr(
        conductor_seed,
        "list_authorized_keys",
        lambda *_a, **_k: {},
    )
    monkeypatch.setattr(
        conductor_seed,
        "_casals_call",
        lambda _cid, method, payload, _net, **_: casals_calls.append((method, payload))
        or {"ok": True},
    )
    monkeypatch.setattr(conductor_seed, "upload_file", lambda *_a, **_k: "uploaded")

    conductor_seed.authorize_gos_entry(
        "qthgp-3yaaa-aaaae-agveq-cai",
        "uq2mu-kaaaa-aaaah-avqcq-cai",
        desc,
        entry,
        "ic",
        repo_root=tmp_path,
    )

    frontend_calls = [
        payload
        for method, payload in casals_calls
        if method == "add_authorized_wasm" and payload.get("kind") == "frontend"
    ]
    assert len(frontend_calls) == 1
    assert frontend_calls[0]["registry_namespace"] == "wasm/realm-assetstorage/main"
