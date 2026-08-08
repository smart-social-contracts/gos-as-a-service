"""Tests for descriptor validation and persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from gaas.descriptor import Descriptor
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID


def test_valid_descriptor_parses() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    assert desc.name == "test"
    assert desc.domain == "test.gos.earth"
    assert desc.gos[0].implementation == "realms-gos"
    assert desc.validate_descriptor() == []


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("name", "Bad Name!", "slug-safe"),
        ("domain", "not a domain", "valid hostname"),
    ],
)
def test_invalid_top_level(field: str, value: object, match: str) -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data[field] = value
    with pytest.raises(ValidationError, match=match):
        Descriptor.model_validate(data)


def test_empty_gos_fails_validation() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    desc.gos = []
    errors = desc.validate_descriptor()
    assert any("at least one" in err for err in errors)


def test_invalid_version_tag() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["gos"] = [{**data["gos"][0], "version": "0.3.1"}]
    with pytest.raises(ValidationError, match="vX.Y.Z|main|latest"):
        Descriptor.model_validate(data)


def test_main_and_latest_version_tags() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["gos"] = [{**data["gos"][0], "version": "main"}]
    data["casals"] = {**data["casals"], "version": "latest"}
    desc = Descriptor.model_validate(data)
    assert desc.gos[0].version == "main"
    assert desc.casals.version == "latest"


def test_invalid_canister_id() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"realm_registry_backend": "not-a-canister"}
    with pytest.raises(ValidationError, match="invalid IC principal"):
        Descriptor.model_validate(data)


def test_unknown_canister_name() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"unknown_canister": VALID_CANISTER_ID}
    with pytest.raises(ValidationError, match="unknown canister"):
        Descriptor.model_validate(data)


def test_services_https_validation() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["services"] = {"billing_url": "http://insecure.example.com"}
    with pytest.raises(ValidationError, match="https"):
        Descriptor.model_validate(data)


def test_services_open_mode_parses() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["services"] = {
        "billing_url": "https://billing.example.com",
        "open_mode": True,
    }
    desc = Descriptor.model_validate(data)
    assert desc.services.open_mode is True


def test_gos_artifact_defaults() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    entry = desc.gos[0]
    assert entry.artifacts.resolved_backend_asset("realms-gos") == "realm_backend.wasm.gz"
    assert entry.artifacts.resolved_frontend_asset("realms-gos") == "realm_frontend.tar.gz"


def test_platform_config_parses() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["platform"] = {
        "version": "v0.3.1",
        "release_repo": "smart-social-contracts/gos-as-a-service",
    }
    desc = Descriptor.model_validate(data)
    assert desc.platform is not None
    assert desc.platform.release_repo.endswith("gos-as-a-service")


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    desc.set_canister_id("realm_registry_frontend", VALID_CANISTER_ID)
    desc.flags["open_mode"] = True
    path = tmp_path / "env.gaas.json"
    desc.save(path)

    loaded = Descriptor.load(path)
    assert loaded.canisters["realm_registry_frontend"] == VALID_CANISTER_ID
    assert loaded.flags["open_mode"] is True
    saved = json.loads(path.read_text())
    assert saved["canisters"]["realm_registry_frontend"] == VALID_CANISTER_ID
    assert saved["flags"]["open_mode"] is True


def test_flags_default_empty_and_round_trip(tmp_path: Path) -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    assert desc.flags == {}
    desc.flags["open_mode"] = True
    path = tmp_path / "flags.gaas.json"
    desc.save(path)
    loaded = Descriptor.load(path)
    assert loaded.flags == {"open_mode": True}
    assert "flags" in json.loads(path.read_text())


def test_atomic_save_replaces_existing(tmp_path: Path) -> None:
    path = tmp_path / "env.gaas.json"
    path.write_text('{"old": true}\n', encoding="utf-8")
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    desc.save(path)
    assert "name" in json.loads(path.read_text())


def test_multisig_config_optional(tmp_path: Path) -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    assert desc.multisig.backend_id is None
    desc.set_multisig_backend_id(VALID_CANISTER_ID)
    assert desc.multisig.backend_id == VALID_CANISTER_ID
    path = tmp_path / "multisig.gaas.json"
    desc.save(path)
    loaded = Descriptor.load(path)
    assert loaded.multisig.backend_id == VALID_CANISTER_ID


def test_casals_commanders_round_trip(tmp_path: Path) -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["casals"] = {
        **data["casals"],
        "commanders": [
            "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
            "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
        ],
    }
    desc = Descriptor.model_validate(data)
    assert desc.casals.commanders == [
        "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
        "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
    ]
    path = tmp_path / "commanders.gaas.json"
    desc.save(path)
    loaded = Descriptor.load(path)
    assert loaded.casals.commanders == desc.casals.commanders


def test_casals_commanders_rejects_invalid_principal() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["casals"] = {**data["casals"], "commanders": ["not-a-principal"]}
    with pytest.raises(ValidationError, match="invalid principal"):
        Descriptor.model_validate(data)


def test_casals_commanders_rejects_empty_entry() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["casals"] = {**data["casals"], "commanders": ["aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa", ""]}
    with pytest.raises(ValidationError, match="non-empty"):
        Descriptor.model_validate(data)


def test_gos_catalog_inherits_from_known() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    entry = desc.gos[0]
    assert "catalog" not in entry.model_fields_set
    catalog = entry.resolved_catalog()
    assert catalog is not None
    assert catalog.codices_repo_suffix == "realms-codices"
    assert catalog.extensions_repo_suffix == "realms-extensions"


def test_gos_catalog_explicit_null_disables_seeding() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["gos"] = [{**data["gos"][0], "catalog": None}]
    desc = Descriptor.model_validate(data)
    entry = desc.gos[0]
    assert "catalog" in entry.model_fields_set
    assert entry.resolved_catalog() is None


def test_gos_catalog_override() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["gos"] = [
        {
            **data["gos"][0],
            "catalog": {
                "codices_repo_suffix": "my-codices",
                "extensions_repo_suffix": "my-extensions",
            },
        }
    ]
    desc = Descriptor.model_validate(data)
    catalog = desc.gos[0].resolved_catalog()
    assert catalog is not None
    assert catalog.codices_repo_suffix == "my-codices"
    assert catalog.extensions_repo_suffix == "my-extensions"


def test_gos_catalog_rejects_invalid_suffix() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["gos"] = [
        {
            **data["gos"][0],
            "catalog": {
                "codices_repo_suffix": "org/repo",
                "extensions_repo_suffix": "realms-extensions",
            },
        }
    ]
    with pytest.raises(ValidationError, match="without '/'"):
        Descriptor.model_validate(data)

