"""Tests for source-build and main artifact wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gaas.phases import phase_seed_file_registry
from gaas.phases import DeployContext
from gaas.descriptor import Descriptor
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID


@pytest.fixture
def descriptor_main() -> Descriptor:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "file_registry": VALID_CANISTER_ID,
        "realm_registry_backend": VALID_CANISTER_ID,
    }
    data["gos"] = [{**data["gos"][0], "version": "main"}]
    return Descriptor.model_validate(data)


def test_resolve_gos_artifacts_main_build_wiring(tmp_path: Path) -> None:
    from gaas.source_build import resolve_gos_artifacts

    backend = tmp_path / "realm_backend.wasm.gz"
    frontend = tmp_path / "realm_frontend.tar.gz"
    backend.write_bytes(b"wasm")
    frontend.write_bytes(b"tar")

    with patch("gaas.source_build.clone_repo") as clone_mock, patch(
        "gaas.source_build.build_realms_gos_artifacts",
        return_value=(backend, frontend),
    ) as build_mock:
        clone_mock.return_value = tmp_path / "clone"
        out_dir = tmp_path / "artifacts"
        got_backend, got_frontend = resolve_gos_artifacts(
            implementation="realms-gos",
            version="main",
            release_repo="smart-social-contracts/realms",
            backend_asset="realm_backend.wasm.gz",
            frontend_asset="realm_frontend.tar.gz",
            dest_dir=out_dir,
            clone_parent=tmp_path / "src-clone",
        )

    clone_mock.assert_called_once_with(
        "smart-social-contracts/realms", tmp_path / "src-clone"
    )
    build_mock.assert_called_once()
    assert got_backend == backend
    assert got_frontend == frontend


def test_phase_seed_file_registry_main_namespace_and_catalog(
    descriptor_main: Descriptor, tmp_path: Path
) -> None:
    backend_file = tmp_path / "realm_backend.wasm.gz"
    frontend_file = tmp_path / "realm_frontend.tar.gz"
    backend_file.write_bytes(b"wasm-bytes")
    frontend_file.write_bytes(b"frontend-bytes")

    ctx = DeployContext(
        identity="deployer",
        network="local",
        work_dir=tmp_path / "work",
        yes=True,
    )

    with patch("gaas.phases.namespace_published", return_value=False), patch(
        "gaas.phases.resolve_gos_artifacts",
        return_value=(backend_file, frontend_file),
    ), patch("gaas.phases.seed_gos_entry") as seed_mock, patch(
        "gaas.phases.ensure_version_catalog_entry", return_value="published"
    ) as catalog_mock, patch(
        "gaas.phases.sha256_file", return_value="abc123"
    ):
        phase_seed_file_registry(descriptor_main, ctx)

    entry = descriptor_main.gos[0]
    seed_mock.assert_called_once()
    args = seed_mock.call_args[0]
    assert args[1] == "wasm/realm-backend/main"
    assert args[2] == "frontend/realm-assets/main"

    catalog_args = catalog_mock.call_args[0]
    assert catalog_args[2] == "main"


def test_resolve_casals_wasm_main_clones_and_builds(tmp_path: Path) -> None:
    from gaas.platform import resolve_casals_wasm

    wasm_path = tmp_path / "casals_conductor.wasm"
    wasm_path.write_bytes(b"wasm")

    with patch("gaas.platform.clone_repo") as clone_mock, patch(
        "gaas.platform.build_casals_wasm", return_value=wasm_path
    ) as build_mock:
        clone_mock.return_value = tmp_path / "clone"
        result = resolve_casals_wasm(
            "main",
            "smart-social-contracts/Casals",
            tmp_path / "casals",
        )

    clone_mock.assert_called_once()
    build_mock.assert_called_once()
    assert result == wasm_path


def test_wizard_validator_accepts_main_and_latest() -> None:
    from gaas.wizard import _validate_version

    assert _validate_version("main") is True
    assert _validate_version("latest") is True
    assert _validate_version("v0.3.1") is True
    assert isinstance(_validate_version("bad"), str)
