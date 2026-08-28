"""Persist descriptor canister IDs into canister_ids.json / dfx.json."""

from __future__ import annotations

import json
from pathlib import Path

from gaas.canister_ids_sync import persist_descriptor_canister_ids
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
