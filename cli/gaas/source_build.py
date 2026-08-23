"""Shallow-clone GitHub repos and build release-equivalent artifacts from source."""

from __future__ import annotations

import gzip
import os
import shutil
import sys
import tarfile
from pathlib import Path

from gaas.artifacts import ArtifactError
from gaas.runlog import run_subprocess

_BASILISK_REQUIREMENTS = [
    "ic-basilisk==0.14.2",
    "ic-basilisk-toolkit==0.5.3",
    "ic-python-db==0.11.0",
    "ic-python-logging==0.3.4",
]


class SourceBuildError(RuntimeError):
    pass


def clone_repo(release_repo: str, dest_parent: Path, *, refresh: bool = False) -> Path:
    """Shallow-clone *release_repo* into *dest_parent* and return the checkout path."""
    slug = release_repo.replace("/", "_")
    dest = dest_parent / slug
    if (dest / ".git").is_dir():
        if refresh:
            run_subprocess(
                ["git", "fetch", "origin", "main", "--depth", "1"],
                cwd=dest,
                check=True,
            )
            run_subprocess(
                ["git", "checkout", "FETCH_HEAD"],
                cwd=dest,
                check=True,
            )
        return dest
    dest_parent.mkdir(parents=True, exist_ok=True)
    run_subprocess(
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


def clone_repo_at_ref(release_repo: str, dest: Path, ref: str) -> Path:
    """Shallow-clone *release_repo* at *ref* into *dest* and return the checkout path."""
    if (dest / ".git").is_dir():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_subprocess(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            ref,
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
    run_subprocess([sys.executable, "-m", "venv", str(venv)], check=True, cwd=repo_root)
    pip = venv / "bin" / "pip"
    run_subprocess([str(pip), "install", "-q", "--upgrade", "pip"], check=True)
    run_subprocess(
        [str(pip), "install", "-q", *list(_BASILISK_REQUIREMENTS)],
        check=True,
    )
    return py


def _tar_directory(source: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as tar:
        for item in sorted(source.iterdir()):
            tar.add(item, arcname=item.name)


def _gzip_wasm_to(dest: Path, wasm_src: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if wasm_src.suffix == ".gz":
        shutil.copy2(wasm_src, dest)
        return
    with wasm_src.open("rb") as src, gzip.open(dest, "wb") as gz:
        shutil.copyfileobj(src, gz)


def _find_monad_backend_wasm(repo_root: Path) -> Path:
    """Locate Motoko backend wasm after ``icp build monad_backend``.

    icp writes the canonical artifact to ``.icp/cache/artifacts/monad_backend``
    (raw wasm, no extension). Do not walk replica state under ``.icp``.
    """
    icp_root = repo_root / ".icp"
    canonical = icp_root / "cache" / "artifacts" / "monad_backend"
    if canonical.is_file():
        return canonical

    candidates: list[Path] = []
    for root in (icp_root / "cache" / "artifacts", icp_root / "canisters"):
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            name = path.name
            if name == "monad_backend" or (
                "monad_backend" in name and name.endswith((".wasm", ".wasm.gz"))
            ):
                candidates.append(path)

    if not candidates:
        raise SourceBuildError(
            "Monad GOS backend build did not produce wasm under "
            f"{icp_root} (expected .icp/cache/artifacts/monad_backend)"
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def build_monad_gos_artifacts(repo_root: Path, dest_dir: Path) -> tuple[Path, Path]:
    """Build Monad GOS release assets from an icp-cli checkout."""
    run_subprocess(["icp", "build", "monad_backend"], cwd=repo_root, check=True)

    backend_src = _find_monad_backend_wasm(repo_root)

    fe_dir = repo_root / "src" / "monad_frontend"
    run_subprocess(["npm", "install"], cwd=fe_dir, check=True)
    run_subprocess(["npm", "run", "build"], cwd=fe_dir, check=True)
    dist = fe_dir / "dist"
    if not dist.is_dir() or not any(dist.iterdir()):
        raise SourceBuildError(f"Monad GOS frontend build did not produce {dist}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    backend_out = dest_dir / "monad_backend.wasm.gz"
    frontend_out = dest_dir / "monad_frontend.tar.gz"
    _gzip_wasm_to(backend_out, backend_src)
    _tar_directory(dist, frontend_out)
    return backend_out, frontend_out


def build_realms_gos_artifacts(repo_root: Path, dest_dir: Path) -> tuple[Path, Path]:
    """Build Realms GOS release assets mirroring ``release.yml``."""
    py = ensure_basilisk_python(repo_root)
    env = {
        **os.environ,
        "CANISTER_CANDID_PATH": str(
            repo_root / "src" / "realm_backend" / "realm_backend.did"
        ),
    }
    run_subprocess(
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
    # Realms is an npm workspace: install at the root so shared deps (vite)
    # are hoisted; installing inside src/realm_frontend leaves a partial tree.
    run_subprocess(
        ["npm", "install", "--legacy-peer-deps"],
        cwd=repo_root,
        check=True,
    )
    # Workspace packages ship source only; realm_frontend imports
    # @realmsgos/extension-bridge which must be compiled (tsc) first.
    run_subprocess(
        ["npm", "run", "build", "-w", "packages/extension-bridge", "--if-present"],
        cwd=repo_root,
        check=True,
    )
    run_subprocess(["npm", "run", "build"], cwd=fe_dir, check=True)
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

    backend_out = dest_dir / "casals_backend.wasm.gz"
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
        repo_root = clone_repo(
            release_repo, clone_parent, refresh=resolved.source_build
        )
        if implementation == "realms-gos":
            backend_file, frontend_file = build_realms_gos_artifacts(
                repo_root, dest_dir
            )
        elif implementation == "monad-gos":
            backend_file, frontend_file = build_monad_gos_artifacts(
                repo_root, dest_dir
            )
        else:
            raise ArtifactError(
                f"source build for {implementation!r} is not supported"
            )
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
