"""Tests for Casals conductor seed helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from gaas import conductor_seed
from gaas.conductor_seed import (
    backends_before_frontends,
    orchestration_template_actions,
    platform_sheet,
)
from gaas.descriptor import Descriptor
from gaas.platform import PlatformError, find_local_assetstorage_wasm
from tests.conftest import SAMPLE_DESCRIPTOR


def test_orchestration_template_actions_skips_when_both_match() -> None:
    digest = "abc123"
    needs_upload, needs_authorize = orchestration_template_actions(digest, digest, digest)
    assert (needs_upload, needs_authorize) == (False, False)


@pytest.mark.parametrize(
    "registry_hash",
    [None, "", "wrong"],
)
def test_orchestration_template_actions_uploads_when_registry_stale(
    registry_hash: str | None,
) -> None:
    digest = "abc123"
    needs_upload, needs_authorize = orchestration_template_actions(digest, registry_hash, digest)
    assert needs_upload is True
    assert needs_authorize is False


def test_orchestration_template_actions_authorizes_when_registry_matches() -> None:
    digest = "abc123"
    needs_upload, needs_authorize = orchestration_template_actions("wrong", digest, digest)
    assert needs_upload is False
    assert needs_authorize is True


def test_platform_sheet_has_infra_and_deployments() -> None:
    sheet = platform_sheet()
    names = [sec["name"] for sec in sheet["sections"]]
    assert names == ["Infra", "Deployments"]
    infra = sheet["sections"][0]
    stand_names = [stand["name"] for stand in infra["stands"]]
    assert stand_names == [
        "governance",
        "orchestration",
        "installer",
        "realm-registry",
    ]
    assert infra["stands"][0]["canisters"][0]["name"] == "multisig"
    assert infra["stands"][0]["canisters"][0]["wasm_type"] == "multisig"
    assert infra["stands"][0]["canisters"][0]["teardown_priority"] == 40
    baton = infra["stands"][1]["canisters"][0]
    assert baton["name"] == "infra-baton"
    assert baton["wasm_type"] == "baton"
    assert baton["install_arg"] == {"top_commander": "$self"}
    assert [c["name"] for c in infra["stands"][2]["canisters"]] == ["realm-installer"]
    assert [c["name"] for c in infra["stands"][3]["canisters"]] == [
        "realm-registry-backend",
        "realm-registry-frontend",
    ]
    assert sheet["sections"][1]["stands"] == []


def test_governance_deploy_sheet_omits_installer_and_registry() -> None:
    from gaas.conductor_seed import governance_deploy_sheet

    sheet = governance_deploy_sheet()
    infra = sheet["sections"][0]
    assert [stand["name"] for stand in infra["stands"]] == [
        "governance",
        "orchestration",
    ]
    full = platform_sheet()
    assert [stand["name"] for stand in full["sections"][0]["stands"]] == [
        "governance",
        "orchestration",
        "installer",
        "realm-registry",
    ]


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


def test_ensure_section_commanders_grants_all_sections(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        conductor_seed,
        "_casals_call",
        lambda _cid, method, payload, _net, **_: calls.append((method, payload))
        or {"ok": True},
    )
    principals = [
        "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
        "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
    ]
    conductor_seed.ensure_section_commanders(
        "qthgp-3yaaa-aaaae-agveq-cai",
        ["Deployments", "Infra"],
        principals,
        "ic",
    )
    assert calls == [
        (
            "set_commander",
            {
                "section": "Deployments",
                "commander_principal": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
            },
        ),
        (
            "set_commander",
            {
                "section": "Deployments",
                "commander_principal": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
            },
        ),
        (
            "set_commander",
            {
                "section": "Infra",
                "commander_principal": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
            },
        ),
        (
            "set_commander",
            {
                "section": "Infra",
                "commander_principal": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
            },
        ),
    ]
    assert all("permissions" not in payload for _, payload in calls)


def test_ensure_section_commanders_noop_when_empty(monkeypatch) -> None:
    called = False

    def _unexpected(*_a, **_k):
        nonlocal called
        called = True
        return {"ok": True}

    monkeypatch.setattr(conductor_seed, "_casals_call", _unexpected)
    conductor_seed.ensure_section_commanders(
        "qthgp-3yaaa-aaaae-agveq-cai",
        ["Deployments"],
        [],
        "ic",
    )
    assert called is False


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
    monkeypatch.setattr(
        dfx,
        "find_assetstorage_wasm",
        lambda: (_ for _ in ()).throw(RuntimeError("download failed")),
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
    assert payload["bundle_namespace"] == "frontend/realm-assets/0.3.1"


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


def test_authorize_gos_entry_monad_gos_backend_uses_motoko_wasm_type(
    tmp_path: Path, monkeypatch
) -> None:
    _write_assetstorage_wasm(tmp_path)
    data = dict(SAMPLE_DESCRIPTOR)
    data["gos"] = [
        {
            "implementation": "monad-gos",
            "version": "main",
            "release_repo": "smart-social-contracts/monad-gos",
            "artifacts": {
                "backend_wasm_key": "monad-backend",
                "frontend_wasm_key": "monad-assets",
            },
            "loader_profile": "monad-iframe-v1",
        }
    ]
    desc = Descriptor.model_validate(data)
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
            {"monad_backend.wasm.gz": "monadhash"}
            if ns == "wasm/monad-backend/main"
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

    backend_calls = [
        payload
        for method, payload in casals_calls
        if method == "add_authorized_wasm" and payload.get("kind") == "backend"
    ]
    assert len(backend_calls) == 1
    assert backend_calls[0]["wasm_type"] == "motoko"
    assert backend_calls[0]["key"] == "monad-backend"


def test_canister_names_collects_all_registered() -> None:
    tree = {
        "sections": [
            {
                "name": "Infra",
                "stands": [
                    {
                        "name": "governance",
                        "canisters": [{"name": "multisig", "canister_id": "aaa"}],
                    },
                    {
                        "name": "platform",
                        "canisters": [
                            {"name": "file-registry", "canister_id": "bbb"},
                        ],
                    },
                ],
            }
        ]
    }
    assert conductor_seed._canister_names(tree) == {"multisig", "file-registry"}


def test_ensure_platform_stand_creates_stand_and_registers(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []
    trees = [
        {"sections": [{"name": "Infra", "stands": []}]},
        {
            "sections": [
                {
                    "name": "Infra",
                    "stands": [
                        {
                            "name": "platform",
                            "canisters": [
                                {
                                    "name": "realm-registry-backend",
                                    "canister_id": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
                                },
                                {
                                    "name": "realm-registry-frontend",
                                    "canister_id": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
                                },
                            ],
                        }
                    ],
                }
            ]
        },
    ]

    def fake_casals(_cid, method, payload, _net, **_):
        calls.append((method, payload))
        return {"ok": True}

    def fake_tree(*_a, **_k):
        return trees.pop(0) if trees else trees[-1]

    monkeypatch.setattr(conductor_seed, "_casals_call", fake_casals)
    monkeypatch.setattr(conductor_seed, "get_tree", fake_tree)

    platform = [
        ("realm-registry-backend", "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa", "backend"),
        ("realm-registry-frontend", "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb", "frontend"),
        ("realm-installer", "ccccc-ccccc-ccccc-ccccc-ccccc-ccc", "backend"),
    ]
    conductor_seed.ensure_platform_stand(
        "qthgp-3yaaa-aaaae-agveq-cai", platform, "ic"
    )

    create_stands = [payload for method, payload in calls if method == "create_stand"]
    assert create_stands == [
        {
            "section": "Infra",
            "name": "realm-registry",
            "description": conductor_seed.PLATFORM_STAND_DESCRIPTIONS["realm-registry"],
        },
        {
            "section": "Infra",
            "name": "installer",
            "description": conductor_seed.PLATFORM_STAND_DESCRIPTIONS["installer"],
        },
    ]
    register_calls = [payload for method, payload in calls if method == "register_canister"]
    assert register_calls == [
        {
            "stand": "realm-registry",
            "name": "realm-registry-backend",
            "canister_id": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
            "kind": "backend",
        },
        {
            "stand": "installer",
            "name": "realm-installer",
            "canister_id": "ccccc-ccccc-ccccc-ccccc-ccccc-ccc",
            "kind": "backend",
        },
        {
            "stand": "realm-registry",
            "name": "realm-registry-frontend",
            "canister_id": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
            "kind": "frontend",
        },
    ]


def test_ensure_platform_stand_tolerates_existing_stand(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def fake_casals(_cid, method, payload, _net, **_):
        if method == "create_stand":
            raise RuntimeError(
                f"stand {payload.get('name')} already exists in section Infra"
            )
        calls.append((method, payload))
        return {"ok": True}

    monkeypatch.setattr(conductor_seed, "_casals_call", fake_casals)
    monkeypatch.setattr(
        conductor_seed,
        "get_tree",
        lambda *_a, **_k: {
            "sections": [{"name": "Infra", "stands": [{"name": "casals-file-registry", "canisters": []}]}]
        },
    )

    conductor_seed.ensure_platform_stand(
        "qthgp-3yaaa-aaaae-agveq-cai",
        [("casals-file-registry", "ddddd-ddddd-ddddd-ddddd-ddddd-ddd", "backend")],
        "ic",
    )
    assert calls == [
        (
            "register_canister",
            {
                "stand": "casals-file-registry",
                "name": "casals-file-registry",
                "canister_id": "ddddd-ddddd-ddddd-ddddd-ddddd-ddd",
                "kind": "backend",
            },
        ),
    ]


def test_ensure_platform_stand_skips_existing_canisters(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        conductor_seed,
        "_casals_call",
        lambda _cid, method, payload, _net, **_: (
            calls.append((method, payload)) or {"ok": True}
            if method != "create_stand"
            else (_ for _ in ()).throw(
                RuntimeError(
                    f"stand {payload.get('name')} already exists in section Infra"
                )
            )
        ),
    )
    monkeypatch.setattr(
        conductor_seed,
        "get_tree",
        lambda *_a, **_k: {
            "sections": [
                {
                    "name": "Infra",
                    "stands": [
                        {
                            "name": "platform",
                            "canisters": [
                                {
                                    "name": "realm-registry-backend",
                                    "canister_id": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
                                },
                                {
                                    "name": "file-registry",
                                    "canister_id": "ddddd-ddddd-ddddd-ddddd-ddddd-ddd",
                                },
                            ],
                        }
                    ],
                }
            ]
        },
    )

    conductor_seed.ensure_platform_stand(
        "qthgp-3yaaa-aaaae-agveq-cai",
        [
            ("realm-registry-backend", "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa", "backend"),
            ("realm-registry-frontend", "eeeee-eeeee-eeeee-eeeee-eeeee-eee", "frontend"),
        ],
        "ic",
    )
    assert calls == [
        (
            "register_canister",
            {
                "stand": "realm-registry",
                "name": "realm-registry-frontend",
                "canister_id": "eeeee-eeeee-eeeee-eeeee-eeeee-eee",
                "kind": "frontend",
            },
        ),
    ]


def test_backends_before_frontends_keeps_relative_order() -> None:
    mixed = [
        ("realm-registry-backend", "a", "backend"),
        ("realm-registry-frontend", "b", "frontend"),
        ("realm-installer", "c", "backend"),
        ("file-registry-frontend", "d", "frontend"),
    ]
    assert backends_before_frontends(mixed) == [
        ("realm-registry-backend", "a", "backend"),
        ("realm-installer", "c", "backend"),
        ("realm-registry-frontend", "b", "frontend"),
        ("file-registry-frontend", "d", "frontend"),
    ]


def test_ensure_platform_stand_unregisters_frontend_before_pending_backends(
    monkeypatch,
) -> None:
    calls: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        conductor_seed,
        "_casals_call",
        lambda _cid, method, payload, _net, **_: (
            calls.append((method, payload)) or {"ok": True}
            if method != "create_stand"
            else (_ for _ in ()).throw(
                RuntimeError(
                    f"stand {payload.get('name')} already exists in section Infra"
                )
            )
        ),
    )
    monkeypatch.setattr(
        conductor_seed,
        "get_tree",
        lambda *_a, **_k: {
            "sections": [
                {
                    "name": "Infra",
                    "stands": [
                        {
                            "name": "platform",
                            "canisters": [
                                {
                                    "name": "realm-registry-backend",
                                    "canister_id": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
                                },
                                {
                                    "name": "realm-registry-frontend",
                                    "canister_id": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
                                },
                            ],
                        }
                    ],
                }
            ]
        },
    )

    conductor_seed.ensure_platform_stand(
        "qthgp-3yaaa-aaaae-agveq-cai",
        [
            ("realm-registry-backend", "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa", "backend"),
            ("realm-registry-frontend", "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb", "frontend"),
            ("realm-installer", "ccccc-ccccc-ccccc-ccccc-ccccc-ccc", "backend"),
        ],
        "ic",
    )
    assert calls == [
        (
            "delete_canister",
            {"canister": "realm-registry-frontend"},
        ),
        (
            "register_canister",
            {
                "stand": "installer",
                "name": "realm-installer",
                "canister_id": "ccccc-ccccc-ccccc-ccccc-ccccc-ccc",
                "kind": "backend",
            },
        ),
        (
            "register_canister",
            {
                "stand": "realm-registry",
                "name": "realm-registry-frontend",
                "canister_id": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
                "kind": "frontend",
            },
        ),
    ]

