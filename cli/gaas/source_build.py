"""Shallow-clone GitHub repos and build release-equivalent artifacts from source."""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from gaas.artifacts import ArtifactError

_BASILISK_REQUIREMENTS = [
    "ic-basilisk==0.14.2",
    "ic-basilisk-toolkit==0.5.3",
    "ic-python-db==0.11.0",
    "ic-python-logging==0.3.4",
]


class SourceBuildError(RuntimeError):
    pass


def clone_repo(release_repo: str, dest_parent: Path) -> Path:
    """Shallow-clone *release_repo* into *dest_parent* and return the checkout path."""
    slug = release_repo.replace("/", "_")
    dest = dest_parent / slug
    if (dest / ".git").is_dir():
        return dest
    dest_parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            f"https://github.com/{release_repo}.git",
            str(dest),
        ],
        check=True,
    )
    return dest


def ensure_basilisk_python(repo_root: Path) -> Path:
    """Return an isolated basilisk venv Python for *repo_root*, creating it if needed."""
    venv = repo_root / ".venv-basilisk"
    py = venv / "bin" / "python"
    if py.is_file():
        return py
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, cwd=repo_root)
    pip = venv / "bin" / "pip"
    subprocess.run([str(pip), "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run(
        [str(pip), "install", "-q", *list(_BASILISK_REQUIREMENTS)],
        check=True,
    )
    return py


def _tar_directory(source: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as tar:
        for item in sorted(source.iterdir()):
            tar.add(item, arcname=item.name)


def build_realms_gos_artifacts(repo_root: Path, dest_dir: Path) -> tuple[Path, Path]:
    """Build Realms GOS release assets mirroring ``release.yml``."""
    py = ensure_basilisk_python(repo_root)
    env = {
        **os.environ,
        "CANISTER_CANDID_PATH": str(
            repo_root / "src" / "realm_backend" / "realm_backend.did"
        ),
    }
    subprocess.run(
        [str(py), "scripts/build_base_wasm.py", "--gzip"],
        cwd=repo_root,
        env=env,
        check=True,
    )
    backend_src = repo_root / ".basilisk" / "realm_backend" / "realm_backend.wasm.gz"
    if not backend_src.is_file():
        raise SourceBuildError(f"Realms backend build did not produce {backend_src}")

    decl_src = repo_root / "src" / "declarations" / "realm_backend"
    decl_dest = repo_root / "src" / "realm_frontend" / "src" / "lib" / "declarations" / "realm_backend"
    if decl_src.is_dir():
        if decl_dest.exists():
            shutil.rmtree(decl_dest)
        shutil.copytree(decl_src, decl_dest)

    fe_dir = repo_root / "src" / "realm_frontend"
    subprocess.run(
        ["npm", "install", "--legacy-peer-deps"],
        cwd=fe_dir,
        check=True,
    )
    subprocess.run(["npm", "run", "build"], cwd=fe_dir, check=True)
    dist = fe_dir / "dist"
    if not dist.is_dir() or not any(dist.iterdir()):
        raise SourceBuildError(f"Realms frontend build did not produce {dist}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    backend_out = dest_dir / "realm_backend.wasm.gz"
    frontend_out = dest_dir / "realm_frontend.tar.gz"
    shutil.copy2(backend_src, backend_out)
    _tar_directory(dist, frontend_out)
    return backend_out, frontend_out


def build_casals_release_artifacts(
    repo_root: Path,
    dest_dir: Path,
    *,
    conductor_canister_id: str = "",
) -> tuple[Path, Path]:
    """Build Casals release assets using the shared local-build helpers."""
    from gaas.platform import build_casals_frontend, build_casals_wasm

    dest_dir.mkdir(parents=True, exist_ok=True)
    wasm_path = build_casals_wasm(repo_root, dest_dir / "wasm_build")
    dist = build_casals_frontend(
        repo_root,
        dest_dir / "frontend_work",
        conductor_canister_id=conductor_canister_id,
    )

    backend_out = dest_dir / "casals_conductor.wasm.gz"
    with gzip.open(backend_out, "wb") as gz, wasm_path.open("rb") as src:
        shutil.copyfileobj(src, gz)

    frontend_out = dest_dir / "casals_frontend.tar.gz"
    _tar_directory(dist, frontend_out)
    return backend_out, frontend_out


def resolve_gos_artifacts(
    *,
    implementation: str,
    version: str,
    release_repo: str,
    backend_asset: str,
    frontend_asset: str,
    dest_dir: Path,
    clone_parent: Path,
    session=None,
) -> tuple[Path, Path]:
    """Fetch or build GOS release assets for seeding the file registry."""
    from gaas.artifacts import fetch_release_assets
    from gaas.versions import resolve_deploy_version

    resolved = resolve_deploy_version(version, release_repo, session=session)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if resolved.source_build:
        if implementation != "realms-gos":
            raise ArtifactError(
                f"source build for {implementation!r} is not supported "
                f"(only realms-gos)"
            )
        repo_root = clone_repo(release_repo, clone_parent)
        backend_file, frontend_file = build_realms_gos_artifacts(repo_root, dest_dir)
        if backend_file.name != backend_asset or frontend_file.name != frontend_asset:
            raise SourceBuildError(
                f"built asset names mismatch: {backend_file.name}, {frontend_file.name}"
            )
        return backend_file, frontend_file

    assets = fetch_release_assets(
        release_repo,
        resolved.fetch_tag or version,
        ["checksums.txt", backend_asset, frontend_asset],
        dest_dir,
        session=session,
    )
    backend_file = next(p for p in assets if p.name == backend_asset)
    frontend_file = next(p for p in assets if p.name == frontend_asset)
    return backend_file, frontend_file
