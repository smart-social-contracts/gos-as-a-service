"""Tests for the gaas seed command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gaas import conductor_seed
from gaas.descriptor import Descriptor
from gaas.main import app
from gaas.phases import (
    SEED_PHASES,
    DeployContext,
    run_seed_phases,
    validate_seed_prerequisites,
)
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID

runner = CliRunner()


def _seed_descriptor(tmp_path: Path, *, canisters: dict[str, str] | None = None) -> Path:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = canisters or {
        "file_registry": VALID_CANISTER_ID,
        "realm_registry_backend": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
        "casals_backend": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
        "realm_registry_frontend": "ccccc-ccccc-ccccc-ccccc-ccccc-ccc",
        "realm_installer": "ddddd-ddddd-ddddd-ddddd-ddddd-ddd",
        "file_registry_frontend": "eeeee-eeeee-eeeee-eeeee-eeeee-eee",
    }
    path = tmp_path / "env.gaas.json"
    Descriptor.model_validate(data).save(path)
    return path


@patch("gaas.main.run_seed_phases")
def test_seed_command_invokes_seed_pipeline(mock_run_seed: MagicMock, tmp_path: Path) -> None:
    path = _seed_descriptor(tmp_path)
    mock_run_seed.return_value = DeployContext(identity="deployer", network="ic")

    result = runner.invoke(
        app,
        ["seed", str(path), "--identity", "deployer", "--network", "ic", "--yes"],
    )

    assert result.exit_code == 0, result.output
    mock_run_seed.assert_called_once()
    desc_arg, ctx_arg = mock_run_seed.call_args[0]
    assert desc_arg.name == "test"
    assert ctx_arg.identity == "deployer"
    assert ctx_arg.network == "ic"
    assert ctx_arg.yes is True


@patch("gaas.phases.phase_seed_conductor")
@patch("gaas.phases.phase_seed_file_registry")
@patch("gaas.phases.phase_create_canisters")
@patch("gaas.phases.phase_validate")
@patch("gaas.phases.phase_seed_validate")
def test_run_seed_phases_runs_only_seed_phases(
    mock_seed_validate: MagicMock,
    mock_validate: MagicMock,
    mock_create: MagicMock,
    mock_seed_registry: MagicMock,
    mock_seed_conductor: MagicMock,
    tmp_path: Path,
) -> None:
    path = _seed_descriptor(tmp_path)
    desc = Descriptor.load(path)
    ctx = DeployContext(identity="deployer", network="ic", yes=True)

    run_seed_phases(desc, ctx)

    mock_validate.assert_not_called()
    mock_create.assert_not_called()
    mock_seed_validate.assert_called_once_with(desc, ctx)
    mock_seed_registry.assert_called_once_with(desc, ctx)
    mock_seed_conductor.assert_called_once_with(desc, ctx)
    assert ctx.completed_phases == [phase_id for phase_id, _, _ in SEED_PHASES]


def test_validate_seed_prerequisites_missing_canisters() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    with pytest.raises(RuntimeError, match="seed requires canister IDs"):
        validate_seed_prerequisites(desc)


def test_validate_seed_prerequisites_missing_binary_registry() -> None:
    """Seed fails early when neither casals_file_registry nor file_registry is set."""
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        name: VALID_CANISTER_ID
        for name in (
            "realm_registry_backend",
            "realm_registry_frontend",
            "realm_installer",
            "casals_backend",
        )
    }
    desc = Descriptor.model_validate(data)
    with pytest.raises(RuntimeError, match="GOS binary registry"):
        validate_seed_prerequisites(desc)


def test_validate_seed_prerequisites_realms_file_registry_optional() -> None:
    """A descriptor without the realms-owned file_registry still validates."""
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        name: VALID_CANISTER_ID
        for name in (
            "realm_registry_backend",
            "realm_registry_frontend",
            "realm_installer",
            "casals_backend",
            "casals_file_registry",
        )
    }
    desc = Descriptor.model_validate(data)
    validate_seed_prerequisites(desc)


@patch("gaas.main.run_seed_phases")
def test_seed_command_missing_canister_ids(mock_run_seed: MagicMock, tmp_path: Path) -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"file_registry": VALID_CANISTER_ID}
    path = tmp_path / "partial.gaas.json"
    Descriptor.model_validate(data).save(path)
    mock_run_seed.side_effect = RuntimeError(
        "seed requires canister IDs in descriptor: casals_backend, realm_registry_backend, "
        "realm_registry_frontend, realm_installer, file_registry_frontend"
    )

    result = runner.invoke(
        app,
        ["seed", str(path), "--identity", "deployer", "--network", "ic"],
    )

    assert result.exit_code == 1
    assert "Seed failed" in result.output
    assert "casals_backend" in result.output


def test_authorize_gos_entry_skips_already_authorized_backend(monkeypatch) -> None:
    casals_calls: list[tuple[str, dict]] = []
    backend_hash = "a" * 64

    monkeypatch.setattr(
        conductor_seed,
        "fetch_namespace_hashes",
        lambda *_a, **_k: {"realm_backend.wasm.gz": backend_hash},
    )
    monkeypatch.setattr(
        conductor_seed,
        "list_authorized_keys",
        lambda *_a, **_k: {"realm-backend@0.3.1": backend_hash},
    )
    monkeypatch.setattr(
        conductor_seed,
        "_casals_call",
        lambda _cid, method, payload, _net, **_: casals_calls.append((method, payload))
        or {"ok": True},
    )
    monkeypatch.setattr(
        conductor_seed,
        "ensure_assetstorage_wasm",
        lambda *_a, **_k: ("wasm/realm-assetstorage/v0.3.1", "realms-assetstorage.wasm.gz", "b" * 64),
    )

    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    entry = desc.gos[0]
    result = conductor_seed.authorize_gos_entry(
        "casals-id",
        VALID_CANISTER_ID,
        desc,
        entry,
        "ic",
    )

    backend_calls = [
        call for call in casals_calls if call[0] == "add_authorized_wasm" and call[1]["kind"] == "backend"
    ]
    assert backend_calls == []
    assert result["backend_status"] == "already_authorized"
    frontend_calls = [
        call for call in casals_calls if call[0] == "add_authorized_wasm" and call[1]["kind"] == "frontend"
    ]
    assert len(frontend_calls) == 1
