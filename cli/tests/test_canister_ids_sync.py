"""Persist descriptor canister IDs into canister_ids.json / dfx.json."""

from __future__ import annotations

import json
from pathlib import Path

from gaas.canister_ids_sync import forget_named_canister_ids, persist_descriptor_canister_ids
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


def test_forget_named_canister_ids_drops_ic_and_env_keys(tmp_path: Path) -> None:
    dead = "5ocwl-eiaaa-aaaah-av2bq-cai"
    keep = "yhw3g-fyaaa-aaaas-qgorq-cai"
    (tmp_path / "canister_ids.json").write_text(
        json.dumps(
            {
                "realm_registry_backend": {
                    "demo": dead,
                    "ic": dead,
                    "test": keep,
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "dfx.json").write_text(
        json.dumps(
            {
                "canisters": {
                    "realm_registry_backend": {
                        "type": "custom",
                        "remote": {
                            "id": {
                                "demo": dead,
                                "ic": dead,
                                "test": keep,
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    forget_named_canister_ids(
        tmp_path, "realm_registry_backend", ["ic", "demo"]
    )

    ids = json.loads((tmp_path / "canister_ids.json").read_text(encoding="utf-8"))
    assert "demo" not in ids["realm_registry_backend"]
    assert "ic" not in ids["realm_registry_backend"]
    assert ids["realm_registry_backend"]["test"] == keep

    dfx = json.loads((tmp_path / "dfx.json").read_text(encoding="utf-8"))
    remote_ids = dfx["canisters"]["realm_registry_backend"]["remote"]["id"]
    assert "demo" not in remote_ids
    assert "ic" not in remote_ids
    assert remote_ids["test"] == keep
