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


def test_ensure_ic_wasm_skips_install_when_on_path(tmp_path: Path) -> None:
    from gaas.source_build import ensure_ic_wasm

    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "ic-wasm").write_text("#!/bin/sh\n")
    (fake / "ic-wasm").chmod(0o755)

    with patch("gaas.source_build.shutil.which", return_value=str(fake / "ic-wasm")), patch(
        "gaas.source_build.run_subprocess"
    ) as run_mock:
        assert ensure_ic_wasm() == fake
    run_mock.assert_not_called()


def test_ensure_ic_wasm_installs_into_local_prefix(tmp_path: Path) -> None:
    from gaas.source_build import ensure_ic_wasm

    prefix = tmp_path / "local"

    def _install(*_args, **_kwargs):
        dest = prefix / "bin"
        dest.mkdir(parents=True)
        (dest / "ic-wasm").write_text("#!/bin/sh\n")
        (dest / "ic-wasm").chmod(0o755)

    with patch("gaas.source_build.shutil.which", return_value=None), patch(
        "gaas.source_build.run_subprocess", side_effect=_install
    ) as run_mock:
        assert ensure_ic_wasm(prefix) == prefix / "bin"

    run_mock.assert_called_once()
    cmd = run_mock.call_args[0][0]
    assert cmd[:4] == ["npm", "install", "-g", "--prefix"]
    assert cmd[4] == str(prefix)
    assert cmd[5] == "@icp-sdk/ic-wasm"


def test_build_realms_gos_artifacts_puts_ic_wasm_on_path(tmp_path: Path) -> None:
    from gaas.source_build import build_realms_gos_artifacts

    repo = tmp_path / "realms"
    (repo / "src" / "realm_backend").mkdir(parents=True)
    (repo / ".basilisk" / "realm_backend").mkdir(parents=True)
    wasm = repo / ".basilisk" / "realm_backend" / "realm_backend.wasm.gz"
    wasm.write_bytes(b"gz")
    dest = tmp_path / "out"
    fe = repo / "src" / "realm_frontend"
    fe.mkdir(parents=True)
    (fe / "dist").mkdir()
    (fe / "dist" / "index.html").write_text("<html></html>")

    captured: dict[str, str] = {}

    def _run(cmd, **kwargs):
        if any("build_base_wasm.py" in str(part) for part in cmd):
            captured["PATH"] = (kwargs.get("env") or {}).get("PATH", "")
        return MagicMock(returncode=0)

    with patch("gaas.source_build.ensure_basilisk_python", return_value=tmp_path / "py"), patch(
        "gaas.source_build.ensure_ic_wasm", return_value=tmp_path / "ic-wasm-bin"
    ), patch("gaas.source_build.run_subprocess", side_effect=_run):
        build_realms_gos_artifacts(repo, dest)

    assert str(tmp_path / "ic-wasm-bin") in captured["PATH"]


def test_resolve_gos_artifacts_main_build_wiring(tmp_path: Path) -> None:
    from gaas.source_build import resolve_gos_artifacts

    backend = tmp_path / "realm_backend.wasm.gz"
    frontend = tmp_path / "realm_frontend.tar.gz"
    backend.write_bytes(b"wasm")
    frontend.write_bytes(b"tar")

    with patch("gaas.source_build.resolve_realms_src", return_value=None), patch(
        "gaas.source_build.clone_repo"
    ) as clone_mock, patch(
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
        "smart-social-contracts/realms", tmp_path / "src-clone", refresh=True
    )
    build_mock.assert_called_once()
    assert got_backend == backend
    assert got_frontend == frontend


def test_resolve_gos_artifacts_monad_gos_main_build_wiring(tmp_path: Path) -> None:
    from gaas.source_build import resolve_gos_artifacts

    backend = tmp_path / "monad_backend.wasm.gz"
    frontend = tmp_path / "monad_frontend.tar.gz"
    backend.write_bytes(b"wasm")
    frontend.write_bytes(b"tar")

    with patch("gaas.source_build.clone_repo") as clone_mock, patch(
        "gaas.source_build.build_monad_gos_artifacts",
        return_value=(backend, frontend),
    ) as build_mock, patch(
        "gaas.source_build.build_realms_gos_artifacts"
    ) as realms_build_mock:
        clone_mock.return_value = tmp_path / "clone"
        out_dir = tmp_path / "artifacts"
        got_backend, got_frontend = resolve_gos_artifacts(
            implementation="monad-gos",
            version="main",
            release_repo="smart-social-contracts/monad-gos",
            backend_asset="monad_backend.wasm.gz",
            frontend_asset="monad_frontend.tar.gz",
            dest_dir=out_dir,
            clone_parent=tmp_path / "src-clone",
        )

    clone_mock.assert_called_once_with(
        "smart-social-contracts/monad-gos", tmp_path / "src-clone", refresh=True
    )
    build_mock.assert_called_once()
    realms_build_mock.assert_not_called()
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
        "gaas.phases.seed_codex_catalog"
    ) as codex_mock, patch(
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
    codex_mock.assert_called_once()


def test_phase_seed_file_registry_main_reseeds_when_already_published(
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

    with patch("gaas.phases.namespace_published", return_value=True), patch(
        "gaas.phases.fetch_namespace_hashes",
        return_value={"realm_backend.wasm.gz": "existing"},
    ), patch(
        "gaas.phases.resolve_gos_artifacts",
        return_value=(backend_file, frontend_file),
    ) as resolve_mock, patch(
        "gaas.phases.seed_gos_entry"
    ) as seed_mock, patch(
        "gaas.phases.seed_codex_catalog"
    ), patch(
        "gaas.phases.ensure_version_catalog_entry", return_value="skipped"
    ), patch(
        "gaas.phases.sha256_file", return_value="fresh-hash"
    ):
        phase_seed_file_registry(descriptor_main, ctx)

    resolve_mock.assert_called_once()
    seed_mock.assert_called_once()


def test_phase_seed_file_registry_pinned_skips_when_already_published(
    tmp_path: Path,
) -> None:
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

    with patch("gaas.phases.namespace_published", return_value=True), patch(
        "gaas.phases.fetch_namespace_hashes",
        return_value={"realm_backend.wasm.gz": "existing"},
    ), patch("gaas.phases.resolve_gos_artifacts") as resolve_mock, patch(
        "gaas.phases.seed_gos_entry"
    ) as seed_mock, patch(
        "gaas.phases.seed_codex_catalog"
    ), patch(
        "gaas.phases.ensure_version_catalog_entry", return_value="skipped"
    ):
        phase_seed_file_registry(descriptor, ctx)

    resolve_mock.assert_not_called()
    seed_mock.assert_not_called()


def test_resolve_gos_artifacts_main_refreshes_existing_clone(tmp_path: Path) -> None:
    from gaas.source_build import resolve_gos_artifacts

    backend = tmp_path / "realm_backend.wasm.gz"
    frontend = tmp_path / "realm_frontend.tar.gz"
    backend.write_bytes(b"wasm")
    frontend.write_bytes(b"tar")

    with patch("gaas.source_build.resolve_realms_src", return_value=None), patch(
        "gaas.source_build.clone_repo"
    ) as clone_mock, patch(
        "gaas.source_build.build_realms_gos_artifacts",
        return_value=(backend, frontend),
    ):
        clone_mock.return_value = tmp_path / "clone"
        resolve_gos_artifacts(
            implementation="realms-gos",
            version="main",
            release_repo="smart-social-contracts/realms",
            backend_asset="realm_backend.wasm.gz",
            frontend_asset="realm_frontend.tar.gz",
            dest_dir=tmp_path / "artifacts",
            clone_parent=tmp_path / "src-clone",
        )

    clone_mock.assert_called_once_with(
        "smart-social-contracts/realms",
        tmp_path / "src-clone",
        refresh=True,
    )


def test_resolve_gos_artifacts_main_prefers_sibling_realms(tmp_path: Path) -> None:
    from gaas.source_build import resolve_gos_artifacts

    backend = tmp_path / "realm_backend.wasm.gz"
    frontend = tmp_path / "realm_frontend.tar.gz"
    backend.write_bytes(b"wasm")
    frontend.write_bytes(b"tar")
    local = tmp_path / "local-realms"

    with patch("gaas.source_build.resolve_realms_src", return_value=local), patch(
        "gaas.source_build.clone_repo"
    ) as clone_mock, patch(
        "gaas.source_build.build_realms_gos_artifacts",
        return_value=(backend, frontend),
    ) as build_mock:
        resolve_gos_artifacts(
            implementation="realms-gos",
            version="main",
            release_repo="smart-social-contracts/realms",
            backend_asset="realm_backend.wasm.gz",
            frontend_asset="realm_frontend.tar.gz",
            dest_dir=tmp_path / "artifacts",
            clone_parent=tmp_path / "src-clone",
        )

    clone_mock.assert_not_called()
    assert build_mock.call_args[0][0] == local


def test_resolve_casals_wasm_main_clones_and_builds(tmp_path: Path) -> None:
    from gaas.platform import resolve_casals_wasm

    wasm_path = tmp_path / "casals_backend.wasm"
    wasm_path.write_bytes(b"wasm")

    with patch("gaas.platform.resolve_casals_src", return_value=None), patch(
        "gaas.platform.clone_repo"
    ) as clone_mock, patch(
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


def test_resolve_casals_wasm_main_prefers_sibling(tmp_path: Path) -> None:
    from gaas.platform import resolve_casals_wasm

    wasm_path = tmp_path / "casals_backend.wasm"
    wasm_path.write_bytes(b"wasm")
    local = tmp_path / "local-casals"

    with patch("gaas.platform.resolve_casals_src", return_value=local), patch(
        "gaas.platform.clone_repo"
    ) as clone_mock, patch(
        "gaas.platform.build_casals_wasm", return_value=wasm_path
    ) as build_mock:
        result = resolve_casals_wasm(
            "main",
            "smart-social-contracts/Casals",
            tmp_path / "casals",
        )

    clone_mock.assert_not_called()
    build_mock.assert_called_once_with(local, tmp_path / "casals")
    assert result == wasm_path


def test_wizard_validator_accepts_main_and_latest() -> None:
    from gaas.wizard import _validate_version

    assert _validate_version("main") is True
    assert _validate_version("latest") is True
    assert _validate_version("v0.3.1") is True
    assert isinstance(_validate_version("bad"), str)
