"""CLI tests for marketplace approval seeding and gaas-env wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from gaas.descriptor import Descriptor
from gaas.file_registry_client import approve_marketplace_namespaces
from gaas.gaas_env import build_gaas_env
from gaas.phases import DeployContext, phase_seed_file_registry
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID


def test_build_gaas_env_defaults_marketplace_to_deployer() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    env = build_gaas_env(desc, "ic", deployer_principal="deployer-principal-id")
    assert env["canisters"]["marketplace_backend"]["ic"] == "deployer-principal-id"


def test_build_gaas_env_keeps_configured_marketplace_canister() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"marketplace_backend": VALID_CANISTER_ID}
    desc = Descriptor.model_validate(data)
    env = build_gaas_env(desc, "ic", deployer_principal="deployer-principal-id")
    assert env["canisters"]["marketplace_backend"]["ic"] == VALID_CANISTER_ID


def test_build_gaas_env_marketplace_override() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["marketplace"] = {"approver_principal": "custom-approver"}
    desc = Descriptor.model_validate(data)
    env = build_gaas_env(desc, "ic", deployer_principal="deployer-principal-id")
    assert env["canisters"]["marketplace_backend"]["ic"] == "custom-approver"


@patch("gaas.file_registry_client.set_namespace_approval")
def test_approve_marketplace_namespaces_filters_prefixes(mock_set: MagicMock) -> None:
    approve_marketplace_namespaces(
        VALID_CANISTER_ID,
        [
            "ext/foo/1.0.0",
            "codex/bar/2.0.0",
            "wasm/realm-backend/main",
            "frontend/realm-assets/main",
        ],
        "local",
        identity="deployer",
    )
    assert mock_set.call_count == 2
    approved = {call.args[1] for call in mock_set.call_args_list}
    assert approved == {"codex/bar/2.0.0", "ext/foo/1.0.0"}


@patch("gaas.phases.approve_marketplace_namespaces")
@patch("gaas.phases.seed_codex_catalog")
@patch("gaas.phases.ensure_version_catalog_entry", return_value="skipped")
@patch("gaas.phases.namespace_published", return_value=True)
@patch("gaas.phases.fetch_namespace_hashes")
def test_phase_seed_file_registry_approves_catalog_namespaces(
    mock_hashes: MagicMock,
    _mock_published: MagicMock,
    _mock_catalog: MagicMock,
    mock_seed_catalog: MagicMock,
    mock_approve: MagicMock,
    tmp_path: Path,
) -> None:
    mock_hashes.return_value = {"realm_backend.wasm.gz": "abc"}
    mock_seed_catalog.return_value = ["ext/syntropia/0.8.9", "ext/voting/1.0.0"]

    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "file_registry": VALID_CANISTER_ID,
        "realm_registry_backend": VALID_CANISTER_ID,
    }
    descriptor = Descriptor.model_validate(data)
    ctx = DeployContext(
        identity="deployer",
        network="local",
        work_dir=tmp_path / "work",
        yes=True,
    )

    phase_seed_file_registry(descriptor, ctx)

    mock_approve.assert_called_once()
    assert mock_approve.call_args.args[1] == [
        "ext/syntropia/0.8.9",
        "ext/voting/1.0.0",
    ]
