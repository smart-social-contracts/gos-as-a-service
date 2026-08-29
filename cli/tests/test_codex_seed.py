"""Tests for codex/extension catalog seeding."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gaas.codex_seed import (
    CodexSeedError,
    collect_codex_uploads,
    collect_extension_uploads,
    ensure_extension_frontend_built,
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
    assert package_namespace("syntropia", "0.8.9", namespace_prefix="codex") == (
        "codex/syntropia/0.8.9"
    )
    assert package_namespace("legacy", "1.0.0", namespace_prefix="codex") == (
        "codex/legacy/1.0.0"
    )


def test_collect_unified_codex_skips_tests_readme_pycache(tmp_path: Path) -> None:
    codex_dir = _write_unified_codex(tmp_path, "syntropia", "0.8.9")
    package_id, version, prefix, uploads = collect_codex_uploads(codex_dir)

    assert package_id == "syntropia"
    assert version == "0.8.9"
    assert prefix == "codex"
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


def test_collect_extension_uploads_includes_html_and_nested_assets(tmp_path: Path) -> None:
    ext_dir = _write_extension(tmp_path, "member_dashboard", "1.1.2")
    dist = ext_dir / "frontend-rt" / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    (dist / "index.js").write_text("export default {};\n", encoding="utf-8")
    (assets / "chunk-abc.js").write_text("console.log('chunk');\n", encoding="utf-8")
    (assets / "chunk-abc.js.map").write_bytes(b"source map")

    uploads = collect_extension_uploads(ext_dir, "member_dashboard")
    paths = {spec.registry_path: spec.local_path for spec in uploads}

    assert set(paths) == {
        "manifest.json",
        "backend/entry.py",
        "frontend/dist/index.html",
        "frontend/dist/index.js",
        "frontend/dist/assets/chunk-abc.js",
    }
    assert paths["frontend/dist/index.html"] == dist / "index.html"
    assert paths["frontend/dist/index.js"] == dist / "index.js"
    assert paths["frontend/dist/assets/chunk-abc.js"] == assets / "chunk-abc.js"


def _write_extension_with_frontend_rt(
    root: Path,
    ext_id: str,
    *,
    with_dist: bool = False,
    with_lock: bool = False,
) -> Path:
    ext_dir = _write_extension(root, ext_id, "1.0.0")
    frontend_rt = ext_dir / "frontend-rt"
    frontend_rt.mkdir()
    (frontend_rt / "package.json").write_text(
        json.dumps({"scripts": {"build": "vite build"}}),
        encoding="utf-8",
    )
    if with_lock:
        (frontend_rt / "package-lock.json").write_text("{}", encoding="utf-8")
    if with_dist:
        dist = frontend_rt / "dist"
        dist.mkdir()
        (dist / "index.js").write_text("export default {};\n", encoding="utf-8")
        (dist / "index.css").write_text("body {}\n", encoding="utf-8")
    return ext_dir


@patch("gaas.codex_seed.run_subprocess")
def test_ensure_extension_frontend_skips_when_dist_present(
    mock_run: MagicMock, tmp_path: Path
) -> None:
    ext_dir = _write_extension_with_frontend_rt(tmp_path, "vault", with_dist=True)

    assert ensure_extension_frontend_built(ext_dir, "vault") is None

    mock_run.assert_not_called()


@patch("gaas.codex_seed.run_subprocess")
def test_ensure_extension_frontend_builds_when_dist_missing(
    mock_run: MagicMock, tmp_path: Path
) -> None:
    ext_dir = _write_extension_with_frontend_rt(
        tmp_path, "public_dashboard", with_lock=True
    )
    dist_index = ext_dir / "frontend-rt" / "dist" / "index.js"

    def _fake_build(cmd, cwd=None, check=None):
        if cmd[:2] == ["npm", "run"]:
            dist = Path(cwd) / "dist"
            dist.mkdir(parents=True, exist_ok=True)
            (dist / "index.js").write_text("built\n", encoding="utf-8")
            (dist / "index.css").write_text("body {}\n", encoding="utf-8")
        return MagicMock(returncode=0)

    mock_run.side_effect = _fake_build

    assert ensure_extension_frontend_built(ext_dir, "public_dashboard") is None

    assert mock_run.call_count == 2
    assert mock_run.call_args_list[0].args[0] == [
        "npm",
        "ci",
        "--no-audit",
        "--no-fund",
    ]
    assert mock_run.call_args_list[1].args[0] == ["npm", "run", "build"]
    uploads = collect_extension_uploads(ext_dir, "public_dashboard")
    paths = {spec.registry_path for spec in uploads}
    assert "frontend/dist/index.js" in paths
    assert "frontend/dist/index.css" in paths
    assert dist_index.is_file()


@patch("gaas.codex_seed.run_subprocess")
def test_ensure_extension_frontend_build_failure_returns_error(
    mock_run: MagicMock, tmp_path: Path
) -> None:
    from gaas.runlog import CommandError

    ext_dir = _write_extension_with_frontend_rt(tmp_path, "broken_ui")
    mock_run.side_effect = CommandError("failed", cmd=["npm", "run", "build"], tail="")

    err = ensure_extension_frontend_built(ext_dir, "broken_ui")

    assert err is not None
    assert "npm build failed" in err
    assert not (ext_dir / "frontend-rt" / "dist" / "index.js").is_file()


@patch("gaas.codex_seed.publish_extension_dir")
@patch("gaas.codex_seed.ensure_extension_frontend_built")
def test_try_seed_extensions_continues_after_build_failure(
    mock_build: MagicMock,
    mock_publish: MagicMock,
    tmp_path: Path,
) -> None:
    from gaas.codex_seed import _try_seed_extensions

    realms = tmp_path / "realms"
    extensions_root = realms / "extensions" / "extensions"
    extensions_root.mkdir(parents=True)
    _write_extension(extensions_root, "good_ext", "1.0.0")
    _write_extension(extensions_root, "bad_ext", "1.0.0")

    mock_build.side_effect = [None, "npm build failed (exit 1)"]
    mock_publish.return_value = "ext/good_ext/1.0.0"

    namespaces = _try_seed_extensions(
        VALID_CANISTER_ID,
        realms,
        "smart-social-contracts/realms",
        tmp_path / "work",
        "main",
        "local",
        identity="deployer",
        catalog=REALMS_CATALOG,
    )

    assert mock_build.call_count == 2
    assert mock_publish.call_count == 2
    assert namespaces == ["ext/good_ext/1.0.0", "ext/good_ext/1.0.0"]


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
        "codex/syntropia/0.8.9",
        "local",
        identity="deployer",
        marketplace_id=None,
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
        marketplace_id=None,
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
        "marketplace_backend": "mmmmm-mmmmm-mmmmm-mmmmm-mmmmm-mmm",
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
    assert kwargs["marketplace_id"] == "mmmmm-mmmmm-mmmmm-mmmmm-mmmmm-mmm"


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
    data["gos"] = [{**data["gos"][0], "catalog": None, "implementation": "monad-gos"}]
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


@patch("gaas.codex_seed.clone_repo_at_ref")
def test_ensure_codices_root_falls_back_to_main_when_tag_missing(
    mock_clone: MagicMock,
    tmp_path: Path,
) -> None:
    from gaas.codex_seed import _ensure_codices_root
    from gaas.runlog import CommandError

    realms = tmp_path / "realms"
    realms.mkdir()

    def _clone(_repo: str, dest: Path, ref: str) -> Path:
        if ref == "v0.4.0":
            raise CommandError("missing ref", cmd=["git", "clone"], tail="")
        dest.mkdir(parents=True)
        _write_unified_codex(dest / "codices", "syntropia", "1.0.0")
        return dest

    mock_clone.side_effect = _clone
    root = _ensure_codices_root(
        realms,
        "smart-social-contracts/realms",
        tmp_path / "work",
        "v0.4.0",
        catalog=REALMS_CATALOG,
    )
    assert root.name == "codices"
    assert mock_clone.call_count == 2
    assert mock_clone.call_args_list[1].args[2] == "main"
