"""Resolve platform and Casals WASM artifacts (local build vs GitHub release)."""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
from pathlib import Path

import requests

from gaas.artifacts import ArtifactError, fetch_release_assets
from gaas.known import (
    CASALS_CONDUCTOR_WASM_ASSET,
    DEFAULT_CASALS_RELEASE_REPO,
    DFX_CANISTER_NAMES,
    PLATFORM_BACKEND_WASMS,
    PLATFORM_FRONTEND_ARCHIVES,
)

_GOS_REPO_MARKERS = ("src/realm_registry_backend", "src/realm_installer", "src/file_registry")


class PlatformError(RuntimeError):
    pass


def find_gos_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "dfx.json").is_file() and all(
            (candidate / marker).exists() for marker in _GOS_REPO_MARKERS
        ):
            return candidate
    raise PlatformError(
        "not inside a gos-as-a-service checkout (dfx.json + platform src/ not found); "
        "set descriptor.platform to fetch release artifacts instead"
    )


def resolve_casals_src(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        path = explicit.resolve()
        if (path / "src" / "main.py").is_file() and (path / "casals_backend.did").is_file():
            return path
        raise PlatformError(f"--casals-src {path} is not a Casals checkout")
    env = os.environ.get("CASALS_SRC", "").strip()
    if env:
        path = Path(env).resolve()
        if (path / "src" / "main.py").is_file():
            return path
    sibling = Path("/srv/dev/Casals")
    if (sibling / "src" / "main.py").is_file():
        return sibling
    return None


def _basilisk_python(casals_root: Path) -> Path:
    venv = casals_root / ".venv-basilisk"
    py = venv / "bin" / "python"
    if py.is_file():
        return py
    alt = Path("/srv/dev/Casals/.venv-basilisk/bin/python")
    if alt.is_file():
        return alt
    raise PlatformError(
        f"Casals basilisk venv not found at {venv} or {alt.parent}; "
        "create it per Casals README before building casals_conductor locally"
    )


def build_casals_wasm(casals_root: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    output = dest / "casals_conductor.wasm"
    if output.is_file():
        return output
    built = casals_root / ".basilisk" / "casals_backend" / "casals_backend.wasm"
    if built.is_file():
        shutil.copy2(built, output)
        return output
    py = _basilisk_python(casals_root)
    env = {
        **os.environ,
        "CANISTER_CANDID_PATH": str(casals_root / "casals_backend.did"),
    }
    subprocess.run(
        [str(py), "-m", "basilisk", "casals_backend", "src/main.py"],
        cwd=casals_root,
        env=env,
        check=True,
    )
    if not built.is_file():
        raise PlatformError(f"Casals basilisk build did not produce {built}")
    shutil.copy2(built, output)
    return output


def fetch_casals_wasm(
    version: str,
    release_repo: str,
    dest: Path,
    *,
    session: requests.Session | None = None,
) -> Path:
    paths = fetch_release_assets(
        release_repo,
        version,
        ["checksums.txt", CASALS_CONDUCTOR_WASM_ASSET],
        dest,
        session=session,
    )
    for path in paths:
        if path.name == CASALS_CONDUCTOR_WASM_ASSET:
            return _ensure_uncompressed_wasm(path)
    raise ArtifactError(f"{CASALS_CONDUCTOR_WASM_ASSET} missing from {release_repo} {version}")


def resolve_casals_wasm(
    version: str,
    release_repo: str,
    dest: Path,
    *,
    casals_src: Path | None = None,
    session: requests.Session | None = None,
) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    cached = dest / "casals_conductor.wasm"
    if cached.is_file():
        return cached
    try:
        return fetch_casals_wasm(version, release_repo, dest, session=session)
    except ArtifactError:
        src = resolve_casals_src(casals_src)
        if src is None:
            raise PlatformError(
                f"Casals release {release_repo}@{version} has no {CASALS_CONDUCTOR_WASM_ASSET}; "
                "provide --casals-src, set CASALS_SRC, or place a checkout at /srv/dev/Casals"
            ) from None
        return build_casals_wasm(src, dest)


def _ensure_uncompressed_wasm(path: Path) -> Path:
    if path.suffix == ".gz" or path.name.endswith(".wasm.gz"):
        out = path.with_suffix("").with_suffix(".wasm")
        if out.is_file() and out.stat().st_mtime >= path.stat().st_mtime:
            return out
        with gzip.open(path, "rb") as src, out.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        return out
    return path


def _local_backend_wasm(repo_root: Path, canister: str) -> Path:
    from gaas import dfx

    dfx_name = DFX_CANISTER_NAMES.get(canister)
    if not dfx_name:
        raise PlatformError(f"no local dfx build mapping for {canister}")
    dfx.build_canister(dfx_name, "local", cwd=repo_root)
    gz = repo_root / ".dfx" / "local" / "canisters" / dfx_name / f"{dfx_name}.wasm.gz"
    if gz.is_file():
        return _ensure_uncompressed_wasm(gz)
    plain = repo_root / ".basilisk" / dfx_name / f"{dfx_name}.wasm"
    if plain.is_file():
        return plain
    raise PlatformError(f"dfx build {dfx_name} did not produce WASM under {repo_root}")


def fetch_platform_backend(
    canister: str,
    platform_version: str,
    release_repo: str,
    dest: Path,
    *,
    session: requests.Session | None = None,
) -> Path:
    asset = PLATFORM_BACKEND_WASMS[canister]
    paths = fetch_release_assets(
        release_repo,
        platform_version,
        ["checksums.txt", asset],
        dest,
        session=session,
    )
    for path in paths:
        if path.name == asset:
            return _ensure_uncompressed_wasm(path)
    raise ArtifactError(f"{asset} missing from platform release {release_repo}@{platform_version}")


def resolve_platform_backend_wasm(
    canister: str,
    *,
    platform_version: str | None,
    release_repo: str,
    work_dir: Path,
    repo_root: Path | None = None,
    session: requests.Session | None = None,
) -> Path:
    dest = work_dir / "platform" / canister
    dest.mkdir(parents=True, exist_ok=True)
    cached = dest / f"{canister}.wasm"
    if cached.is_file():
        return cached
    if platform_version:
        wasm = fetch_platform_backend(
            canister, platform_version, release_repo, dest, session=session
        )
        if wasm != cached:
            shutil.copy2(wasm, cached)
        return cached
    root = repo_root or find_gos_repo_root()
    wasm = _local_backend_wasm(root, canister)
    shutil.copy2(wasm, cached)
    return cached


def fetch_platform_frontend_archive(
    canister: str,
    platform_version: str,
    release_repo: str,
    dest: Path,
    *,
    session: requests.Session | None = None,
) -> Path:
    asset = PLATFORM_FRONTEND_ARCHIVES[canister]
    paths = fetch_release_assets(
        release_repo,
        platform_version,
        ["checksums.txt", asset],
        dest,
        session=session,
    )
    for path in paths:
        if path.name == asset:
            return path
    raise ArtifactError(f"{asset} missing from platform release {release_repo}@{platform_version}")


def frontend_dist_dir(
    canister: str,
    *,
    platform_version: str | None,
    release_repo: str,
    work_dir: Path,
    repo_root: Path,
    session: requests.Session | None = None,
) -> Path:
    if canister == "realm_registry_frontend":
        return repo_root / "src" / "realm_registry_frontend" / "dist"
    if canister == "file_registry_frontend":
        return repo_root / "src" / "file_registry_frontend" / "dist"
    raise PlatformError(f"unknown frontend canister {canister}")
