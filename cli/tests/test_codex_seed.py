"""Tests for codex/extension catalog seeding."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gaas.codex_seed import (
    CodexSeedError,
    collect_codex_uploads,
    collect_extension_uploads,
    list_codices,
    package_namespace,
    publish_codex_dir,
    publish_extension_dir,
    seed_codex_catalog,
)
from gaas.descriptor import Descriptor
from gaas.known import GOS_IMPLEMENTATIONS
from gaas.phases import DeployContext, phase_seed_file_registry
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID

REALMS_CATALOG = GOS_IMPLEMENTATIONS["realms-gos"].catalog
assert REALMS_CATALOG is not None


def _write_unified_codex(root: Path, codex_id: str, version: str) -> Path:
    codex_dir = root / codex_id
    backend = codex_dir / "backend"
    backend.mkdir(parents=True)
    (codex_dir / "manifest.json").write_text(
        json.dumps({"id": codex_id, "version": version, "kind": "codex"}),
        encoding="utf-8",
    )
    (backend / "entry.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (backend / "data.json").write_text("{}", encoding="utf-8")
    (codex_dir / "tests").mkdir()
    (codex_dir / "tests" / "test_sample.py").write_text("def test_x(): pass\n")
    (codex_dir / "README.md").write_text("# docs\n", encoding="utf-8")
    (codex_dir / "backend" / "__pycache__").mkdir()
    (codex_dir / "backend" / "__pycache__" / "entry.cpython-311.pyc").write_bytes(
        b"cache"
    )
    return codex_dir


def _write_legacy_codex(root: Path, codex_id: str, version: str) -> Path:
    codex_dir = root / codex_id
    codex_dir.mkdir(parents=True)
    (codex_dir / "manifest.json").write_text(
        json.dumps({"id": codex_id, "version": version}),
        encoding="utf-8",
    )
    (codex_dir / "hooks.py").write_text("x = 1\n", encoding="utf-8")
    return codex_dir


def _write_extension(root: Path, ext_id: str, version: str) -> Path:
    ext_dir = root / ext_id
    backend = ext_dir / "backend"
    backend.mkdir(parents=True)
    (ext_dir / "manifest.json").write_text(
        json.dumps({"id": ext_id, "version": version}),
        encoding="utf-8",
    )
    (backend / "entry.py").write_text("def run(): pass\n", encoding="utf-8")
    return ext_dir


def test_package_namespace_conventions() -> None:
    assert package_namespace("syntropia", "0.8.9", namespace_prefix="ext") == (
        "ext/syntropia/0.8.9"
    )
    assert package_namespace("legacy", "1.0.0", namespace_prefix="codex") == (
        "codex/legacy/1.0.0"
    )


def test_collect_unified_codex_skips_tests_readme_pycache(tmp_path: Path) -> None:
    codex_dir = _write_unified_codex(tmp_path, "syntropia", "0.8.9")
    package_id, version, prefix, uploads = collect_codex_uploads(codex_dir)

    assert package_id == "syntropia"
    assert version == "0.8.9"
    assert prefix == "ext"
    paths = {spec.registry_path for spec in uploads}
    assert paths == {"manifest.json", "backend/entry.py", "backend/data.json"}
    assert not any("tests/" in path for path in paths)
    assert not any("__pycache__" in path for path in paths)
    assert "README.md" not in paths


def test_collect_legacy_codex_uploads_py_and_json_only(tmp_path: Path) -> None:
    codex_dir = _write_legacy_codex(tmp_path, "legacy", "2.0.0")
    package_id, version, prefix, uploads = collect_codex_uploads(codex_dir)

    assert package_id == "legacy"
    assert version == "2.0.0"
    assert prefix == "codex"
    paths = {spec.registry_path for spec in uploads}
    assert paths == {"manifest.json", "hooks.py"}


def test_collect_extension_uploads_backend_only(tmp_path: Path) -> None:
    ext_dir = _write_extension(tmp_path, "voting", "1.2.3")
    uploads = collect_extension_uploads(ext_dir, "voting")
    paths = {spec.registry_path for spec in uploads}
    assert paths == {"manifest.json", "backend/entry.py"}


def test_list_codices_skips_common_dirs(tmp_path: Path) -> None:
    root = tmp_path / "codices"
    root.mkdir()
    _write_unified_codex(root, "syntropia", "0.8.9")
    (root / "_common").mkdir()
    (root / "common").mkdir()
    (root / "empty").mkdir()

    names = [path.name for path in list_codices(root)]
    assert names == ["syntropia"]


@patch("gaas.codex_seed.publish_namespace")
@patch("gaas.codex_seed.upload_file")
@patch("gaas.codex_seed.fetch_namespace_hashes")
def test_publish_codex_dir_idempotent_skip(
    mock_hashes: MagicMock,
    mock_upload: MagicMock,
    mock_publish: MagicMock,
    tmp_path: Path,
) -> None:
    codex_dir = _write_unified_codex(tmp_path, "syntropia", "0.8.9")
    mock_hashes.return_value = {
        "manifest.json": "aaa",
        "backend/entry.py": "bbb",
        "backend/data.json": "ccc",
    }
    mock_upload.return_value = "skipped"

    publish_codex_dir(
        VALID_CANISTER_ID,
        codex_dir,
        "local",
        identity="deployer",
    )

    assert mock_upload.call_count == 3
    mock_publish.assert_not_called()


@patch("gaas.codex_seed.publish_namespace")
@patch("gaas.codex_seed.upload_file")
@patch("gaas.codex_seed.fetch_namespace_hashes")
def test_publish_codex_dir_publishes_namespace_on_upload(
    mock_hashes: MagicMock,
    mock_upload: MagicMock,
    mock_publish: MagicMock,
    tmp_path: Path,
) -> None:
    codex_dir = _write_unified_codex(tmp_path, "syntropia", "0.8.9")
    mock_hashes.return_value = {}
    mock_upload.side_effect = ["uploaded", "skipped", "skipped"]

    publish_codex_dir(
        VALID_CANISTER_ID,
        codex_dir,
        "local",
        identity="deployer",
    )

    mock_publish.assert_called_once_with(
        VALID_CANISTER_ID,
        "ext/syntropia/0.8.9",
        "local",
        identity="deployer",
    )


@patch("gaas.codex_seed.publish_namespace")
@patch("gaas.codex_seed.upload_file")
@patch("gaas.codex_seed.fetch_namespace_hashes")
def test_publish_extension_dir_namespace(
    mock_hashes: MagicMock,
    mock_upload: MagicMock,
    mock_publish: MagicMock,
    tmp_path: Path,
) -> None:
    ext_dir = _write_extension(tmp_path, "package_manager", "0.5.0")
    mock_hashes.return_value = {}
    mock_upload.return_value = "uploaded"

    publish_extension_dir(
        VALID_CANISTER_ID,
        ext_dir,
        "local",
        identity="deployer",
    )

    mock_publish.assert_called_once_with(
        VALID_CANISTER_ID,
        "ext/package_manager/0.5.0",
        "local",
        identity="deployer",
    )


@patch("gaas.codex_seed._try_seed_extensions")
@patch("gaas.codex_seed.publish_codex_dir")
@patch("gaas.codex_seed._ensure_codices_root")
@patch("gaas.codex_seed.resolve_realms_checkout")
def test_seed_codex_catalog_hard_fails_on_codex_error(
    mock_checkout: MagicMock,
    mock_codices_root: MagicMock,
    mock_publish_codex: MagicMock,
    _mock_ext: MagicMock,
    tmp_path: Path,
) -> None:
    realms = tmp_path / "realms"
    codices = tmp_path / "codices"
    codices.mkdir()
    _write_unified_codex(codices, "syntropia", "0.8.9")
    mock_checkout.return_value = realms
    mock_codices_root.return_value = codices
    mock_publish_codex.side_effect = CodexSeedError("syntropia: 1 upload(s) failed")

    with pytest.raises(CodexSeedError, match="codex publish failed"):
        seed_codex_catalog(
            VALID_CANISTER_ID,
            "smart-social-contracts/realms",
            "main",
            tmp_path / "work",
            "local",
            identity="deployer",
            catalog=REALMS_CATALOG,
        )


@patch("gaas.phases.seed_codex_catalog")
@patch("gaas.phases.ensure_version_catalog_entry", return_value="skipped")
@patch("gaas.phases.namespace_published", return_value=True)
@patch("gaas.phases.fetch_namespace_hashes")
def test_phase_seed_file_registry_wires_codex_catalog(
    mock_hashes: MagicMock,
    _mock_published: MagicMock,
    _mock_catalog: MagicMock,
    mock_seed_catalog: MagicMock,
    tmp_path: Path,
) -> None:
    mock_hashes.return_value = {"realm_backend.wasm.gz": "abc"}

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

    mock_seed_catalog.assert_called_once()
    args = mock_seed_catalog.call_args[0]
    kwargs = mock_seed_catalog.call_args.kwargs
    assert args[0] == VALID_CANISTER_ID
    assert args[1] == "smart-social-contracts/realms"
    assert kwargs["catalog"] == REALMS_CATALOG


@patch("gaas.phases.seed_codex_catalog")
@patch("gaas.phases.ensure_version_catalog_entry", return_value="skipped")
@patch("gaas.phases.namespace_published", return_value=True)
@patch("gaas.phases.fetch_namespace_hashes")
def test_phase_seed_file_registry_skips_without_catalog(
    mock_hashes: MagicMock,
    _mock_published: MagicMock,
    _mock_version_catalog: MagicMock,
    mock_seed_catalog: MagicMock,
    tmp_path: Path,
) -> None:
    mock_hashes.return_value = {"realm_backend.wasm.gz": "abc"}

    data = dict(SAMPLE_DESCRIPTOR)
    data["gos"] = [{**data["gos"][0], "catalog": None, "implementation": "chora-gos"}]
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

    mock_seed_catalog.assert_not_called()


@patch("gaas.phases.seed_codex_catalog")
@patch("gaas.phases.ensure_version_catalog_entry", return_value="skipped")
@patch("gaas.phases.namespace_published", return_value=True)
@patch("gaas.phases.fetch_namespace_hashes")
def test_phase_seed_file_registry_honors_catalog_override(
    mock_hashes: MagicMock,
    _mock_published: MagicMock,
    _mock_version_catalog: MagicMock,
    mock_seed_catalog: MagicMock,
    tmp_path: Path,
) -> None:
    mock_hashes.return_value = {"realm_backend.wasm.gz": "abc"}

    override = {
        "codices_repo_suffix": "custom-codices",
        "extensions_repo_suffix": "custom-extensions",
    }
    data = dict(SAMPLE_DESCRIPTOR)
    data["gos"] = [{**data["gos"][0], "catalog": override}]
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

    mock_seed_catalog.assert_called_once()
    catalog = mock_seed_catalog.call_args.kwargs["catalog"]
    assert catalog.codices_repo_suffix == "custom-codices"
    assert catalog.extensions_repo_suffix == "custom-extensions"
