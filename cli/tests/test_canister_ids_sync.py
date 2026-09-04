"""Persist descriptor canister IDs into canister_ids.json / dfx.json."""

from __future__ import annotations

import json
from pathlib import Path

from gaas.canister_ids_sync import align_ic_alias, persist_descriptor_canister_ids
from gaas.descriptor import Descriptor
from tests.conftest import SAMPLE_DESCRIPTOR

LIVE_CASALS = "to4on-xyaaa-aaaan-q6n5a-cai"
DEAD_CASALS = "fdr7z-3aaaa-aaaae-ag23a-cai"


def _staging_descriptor() -> Descriptor:
    data = dict(SAMPLE_DESCRIPTOR)
    data["name"] = "staging"
    data["domain"] = "staging.gos.earth"
    data["canisters"] = {
        "casals_frontend": LIVE_CASALS,
        "casals_backend": "th7fr-bqaaa-aaaan-q6n4q-cai",
    }
    return Descriptor.model_validate(data)


def test_persist_writes_descriptor_name_not_ic(tmp_path: Path) -> None:
    (tmp_path / "canister_ids.json").write_text(
        json.dumps(
            {
                "casals_frontend": {
                    "staging": DEAD_CASALS,
                    "test": "qic2k-baaaa-aaaae-agvga-cai",
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "dfx.json").write_text(
        json.dumps(
            {
                "canisters": {
                    "casals_frontend": {
                        "source": ["casals_frontend_dist"],
                        "type": "assets",
                        "remote": {
                            "id": {
                                "staging": DEAD_CASALS,
                                "test": "qic2k-baaaa-aaaae-agvga-cai",
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    persist_descriptor_canister_ids(tmp_path, _staging_descriptor())

    ids = json.loads((tmp_path / "canister_ids.json").read_text(encoding="utf-8"))
    assert ids["casals_frontend"]["staging"] == LIVE_CASALS
    assert ids["casals_frontend"]["test"] == "qic2k-baaaa-aaaae-agvga-cai"
    assert "ic" not in ids["casals_frontend"]
    assert DEAD_CASALS not in json.dumps(ids)

    dfx = json.loads((tmp_path / "dfx.json").read_text(encoding="utf-8"))
    assert dfx["canisters"]["casals_frontend"]["remote"]["id"]["staging"] == LIVE_CASALS
    assert dfx["canisters"]["casals_frontend"]["remote"]["id"]["test"] == (
        "qic2k-baaaa-aaaae-agvga-cai"
    )


def test_persist_creates_canister_ids_when_missing(tmp_path: Path) -> None:
    persist_descriptor_canister_ids(tmp_path, _staging_descriptor())
    ids = json.loads((tmp_path / "canister_ids.json").read_text(encoding="utf-8"))
    assert ids["casals_frontend"]["staging"] == LIVE_CASALS
    assert ids["casals_backend"]["staging"] == "th7fr-bqaaa-aaaan-q6n4q-cai"


def test_persist_local_does_not_write_dfx_remote_id(tmp_path: Path) -> None:
    """A local replica ID in remote.id.local makes dfx skip the WASM build."""
    (tmp_path / "dfx.json").write_text(
        json.dumps(
            {
                "canisters": {
                    "realm_registry_backend": {
                        "type": "custom",
                        "wasm": ".basilisk/realm_registry_backend/realm_registry_backend.wasm",
                        "remote": {
                            "id": {
                                "staging": "snqhl-daaaa-aaaan-q6n3q-cai",
                                "test": "yhw3g-fyaaa-aaaas-qgorq-cai",
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    data = dict(SAMPLE_DESCRIPTOR)
    data["name"] = "local"
    data["domain"] = "local.localhost"
    data["canisters"] = {
        "realm_registry_backend": "uqqxf-5h777-77774-qaaaa-cai",
        "casals_frontend": "umunu-kh777-77774-qaaca-cai",
    }
    persist_descriptor_canister_ids(tmp_path, Descriptor.model_validate(data))

    ids = json.loads((tmp_path / "canister_ids.json").read_text(encoding="utf-8"))
    assert ids["realm_registry_backend"]["local"] == "uqqxf-5h777-77774-qaaaa-cai"
    dfx = json.loads((tmp_path / "dfx.json").read_text(encoding="utf-8"))
    remote_ids = dfx["canisters"]["realm_registry_backend"]["remote"]["id"]
    assert "local" not in remote_ids
    assert remote_ids["staging"] == "snqhl-daaaa-aaaan-q6n3q-cai"


def _ids_file(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "canister_ids.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _descriptor(name: str, canisters: dict) -> Descriptor:
    data = dict(SAMPLE_DESCRIPTOR)
    data["name"] = name
    data["domain"] = f"{name}.gos.earth"
    data["canisters"] = canisters
    return Descriptor.model_validate(data)


def test_align_ic_alias_repoints_another_environments_id(tmp_path: Path) -> None:
    """The bug: staging's named create returned test's live installer.

    dfx keys canister_ids.json by network, and test/staging/demo all deploy with
    --network ic, so they shared one "ic" row. Deploying staging must not leave
    test's id there.
    """
    _ids_file(
        tmp_path,
        {
            "realm_installer": {
                "ic": "iupx4-uaaaa-aaaai-ax5ua-cai",
                "test": "iupx4-uaaaa-aaaai-ax5ua-cai",
            }
        },
    )
    desc = _descriptor("staging", {"realm_installer": "ta6df-miaaa-aaaan-q6n4a-cai"})

    changed = align_ic_alias(tmp_path, desc)

    ids = json.loads((tmp_path / "canister_ids.json").read_text(encoding="utf-8"))
    assert ids["realm_installer"]["ic"] == "ta6df-miaaa-aaaan-q6n4a-cai"
    assert ids["realm_installer"]["test"] == "iupx4-uaaaa-aaaai-ax5ua-cai"
    assert changed["realm_installer"] == (
        "iupx4-uaaaa-aaaai-ax5ua-cai",
        "ta6df-miaaa-aaaan-q6n4a-cai",
    )


def test_align_ic_alias_drops_row_the_descriptor_has_no_id_for(tmp_path: Path) -> None:
    """A named create must mint, not adopt another environment's canister."""
    _ids_file(
        tmp_path,
        {"realm_installer": {"ic": "iupx4-uaaaa-aaaai-ax5ua-cai", "test": "iupx4-uaaaa-aaaai-ax5ua-cai"}},
    )
    desc = _descriptor("staging", {})

    align_ic_alias(tmp_path, desc)

    ids = json.loads((tmp_path / "canister_ids.json").read_text(encoding="utf-8"))
    assert "ic" not in ids["realm_installer"]
    assert ids["realm_installer"]["test"] == "iupx4-uaaaa-aaaai-ax5ua-cai"


def test_align_ic_alias_is_noop_when_already_aligned(tmp_path: Path) -> None:
    _ids_file(tmp_path, {"realm_installer": {"ic": "ta6df-miaaa-aaaan-q6n4a-cai"}})
    desc = _descriptor("staging", {"realm_installer": "ta6df-miaaa-aaaan-q6n4a-cai"})
    assert align_ic_alias(tmp_path, desc) == {}


def test_align_ic_alias_tolerates_missing_file(tmp_path: Path) -> None:
    assert align_ic_alias(tmp_path, _descriptor("staging", {})) == {}


def test_persist_leaves_the_ic_alias_to_alignment(tmp_path: Path) -> None:
    """persist writes env-keyed rows only; align_ic_alias owns the "ic" row.

    Splitting it that way keeps persist from resurrecting an "ic" row for an
    environment mid-run, while alignment still repoints a stale one at the start.
    """
    _ids_file(tmp_path, {"realm_installer": {"ic": "iupx4-uaaaa-aaaai-ax5ua-cai"}})
    desc = _descriptor("staging", {"realm_installer": "ta6df-miaaa-aaaan-q6n4a-cai"})

    persist_descriptor_canister_ids(tmp_path, desc)
    ids = json.loads((tmp_path / "canister_ids.json").read_text(encoding="utf-8"))
    assert ids["realm_installer"]["staging"] == "ta6df-miaaa-aaaan-q6n4a-cai"
    assert ids["realm_installer"]["ic"] == "iupx4-uaaaa-aaaai-ax5ua-cai"

    align_ic_alias(tmp_path, desc)
    ids = json.loads((tmp_path / "canister_ids.json").read_text(encoding="utf-8"))
    assert ids["realm_installer"]["ic"] == "ta6df-miaaa-aaaan-q6n4a-cai"
