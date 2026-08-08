"""Resolve platform and Casals WASM artifacts (local build vs GitHub release)."""

from __future__ import annotations

import gzip
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
from pathlib import Path

import requests

from gaas.artifacts import ArtifactError, fetch_release_assets
from gaas.known import (
    CASALS_BACKEND_WASM_ASSET,
    CASALS_FRONTEND_ARCHIVE,
    DEFAULT_CASALS_RELEASE_REPO,
    DFX_CANISTER_NAMES,
    PLATFORM_BACKEND_WASMS,
    PLATFORM_FRONTEND_ARCHIVES,
)
from gaas.source_build import clone_repo
from gaas.versions import resolve_deploy_version

_GOS_REPO_MARKERS = ("src/realm_registry_backend", "src/realm_installer", "src/file_registry")

_BASILISK_REQUIREMENTS = [
    "ic-basilisk==0.14.2",
    "ic-basilisk-toolkit==0.5.3",
    "ic-python-db==0.11.0",
    "ic-python-logging==0.3.4",
]


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
    if alt.is_file() and casals_root == Path("/srv/dev/Casals").resolve():
        return alt
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, cwd=casals_root)
    pip = venv / "bin" / "pip"
    subprocess.run([str(pip), "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run(
        [str(pip), "install", "-q", *list(_BASILISK_REQUIREMENTS)],
        check=True,
    )
    if not py.is_file():
        raise PlatformError(
            f"Casals basilisk venv not found at {venv}; "
            "create it per Casals README before building casals_backend locally"
        )
    return py


def build_casals_wasm(casals_root: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    output = dest / "casals_backend.wasm"
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
        ["checksums.txt", CASALS_BACKEND_WASM_ASSET],
        dest,
        session=session,
    )
    for path in paths:
        if path.name == CASALS_BACKEND_WASM_ASSET:
            return _ensure_uncompressed_wasm(path)
    raise ArtifactError(f"{CASALS_BACKEND_WASM_ASSET} missing from {release_repo} {version}")


def build_casals_frontend(
    casals_root: Path,
    work_dir: Path,
    *,
    conductor_canister_id: str = "",
) -> Path:
    dest = work_dir / "casals_frontend_dist"
    if dest.is_dir() and any(dest.iterdir()):
        return dest
    frontend_dir = casals_root / "frontend"
    env = {**os.environ}
    if conductor_canister_id:
        env["VITE_CANISTER_ID"] = conductor_canister_id
    subprocess.run(["npm", "ci"], cwd=frontend_dir, check=True, env=env)
    subprocess.run(["npm", "run", "build"], cwd=frontend_dir, check=True, env=env)
    built = casals_root / "dist"
    if not built.is_dir() or not any(built.iterdir()):
        raise PlatformError(f"Casals frontend build did not produce {built}")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(built, dest)
    return dest


def fetch_casals_frontend_archive(
    version: str,
    release_repo: str,
    dest: Path,
    *,
    session: requests.Session | None = None,
) -> Path:
    paths = fetch_release_assets(
        release_repo,
        version,
        ["checksums.txt", CASALS_FRONTEND_ARCHIVE],
        dest,
        session=session,
    )
    for path in paths:
        if path.name == CASALS_FRONTEND_ARCHIVE:
            return path
    raise ArtifactError(
        f"{CASALS_FRONTEND_ARCHIVE} missing from {release_repo} {version}"
    )


def _casals_ic_env_cookie_value(conductor_id: str, frontend_id: str = "") -> str:
    """URL-encoded ic_env cookie body (certified-assets / Casals api.ts format)."""
    pairs = ["ic_root_key=", f"PUBLIC_CANISTER_ID:casals_backend={conductor_id}"]
    if frontend_id:
        pairs.append(f"PUBLIC_CANISTER_ID:casals_frontend={frontend_id}")
    return urllib.parse.quote("&".join(pairs), safe="")


def _inject_casals_ic_env_assets(
    dist_dir: Path,
    conductor_id: str,
    frontend_id: str = "",
) -> None:
    """Set ic_env via .ic-assets.json5 for prebuilt Casals frontend (release tarball).

    Local builds bake VITE_CANISTER_ID instead. This relies on the assets canister
    applying custom Set-Cookie headers on HTML responses.
    """
    cookie_val = _casals_ic_env_cookie_value(conductor_id, frontend_id)
    config = [
        {
            "match": "**/*.{html,shtml}",
            "headers": {
                "Set-Cookie": f"ic_env={cookie_val}; SameSite=Lax",
            },
        },
    ]
    (dist_dir / ".ic-assets.json5").write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )


def resolve_casals_frontend_dist(
    version: str,
    release_repo: str,
    dest: Path,
    *,
    casals_src: Path | None = None,
    session: requests.Session | None = None,
    conductor_canister_id: str = "",
    frontend_canister_id: str = "",
) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    cached = dest / "dist"
    if cached.is_dir() and any(cached.iterdir()):
        return cached

    resolved = resolve_deploy_version(version, release_repo, session=session)
    if resolved.source_build:
        repo_root = clone_repo(release_repo, dest.parent / "src-clone")
        built = build_casals_frontend(
            repo_root, dest, conductor_canister_id=conductor_canister_id
        )
        if conductor_canister_id:
            _inject_casals_ic_env_assets(
                built, conductor_canister_id, frontend_canister_id
            )
        return built

    try:
        archive = fetch_casals_frontend_archive(
            resolved.fetch_tag or version, release_repo, dest, session=session
        )
        cached.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(cached)
        if conductor_canister_id:
            _inject_casals_ic_env_assets(
                cached, conductor_canister_id, frontend_canister_id
            )
        return cached
    except ArtifactError:
        src = resolve_casals_src(casals_src)
        if src is None:
            raise PlatformError(
                f"Casals release {release_repo}@{version} has no "
                f"{CASALS_FRONTEND_ARCHIVE}; provide --casals-src, set CASALS_SRC, "
                "or place a checkout at /srv/dev/Casals"
            ) from None
        return build_casals_frontend(
            src, dest, conductor_canister_id=conductor_canister_id
        )


def resolve_casals_wasm(
    version: str,
    release_repo: str,
    dest: Path,
    *,
    casals_src: Path | None = None,
    session: requests.Session | None = None,
) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    cached = dest / "casals_backend.wasm"
    if cached.is_file():
        return cached

    resolved = resolve_deploy_version(version, release_repo, session=session)
    if resolved.source_build:
        repo_root = clone_repo(release_repo, dest.parent / "src-clone")
        return build_casals_wasm(repo_root, dest)

    try:
        return fetch_casals_wasm(
            resolved.fetch_tag or version, release_repo, dest, session=session
        )
    except ArtifactError:
        src = resolve_casals_src(casals_src)
        if src is None:
            raise PlatformError(
                f"Casals release {release_repo}@{version} has no {CASALS_BACKEND_WASM_ASSET}; "
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


def _basilisk_env(repo_root: Path) -> dict[str, str] | None:
    """Put the repo's .venv-basilisk first on PATH so `python -m basilisk` uses it."""
    venv_bin = repo_root / ".venv-basilisk" / "bin"
    if venv_bin.is_dir():
        return {"PATH": f"{venv_bin}{os.pathsep}{os.environ.get('PATH', '')}"}
    return None


def _local_backend_wasm(repo_root: Path, canister: str) -> Path:
    from gaas import dfx

    dfx_name = DFX_CANISTER_NAMES.get(canister)
    if not dfx_name:
        raise PlatformError(f"no local dfx build mapping for {canister}")
    dfx.build_canister(dfx_name, "local", cwd=repo_root, env_extra=_basilisk_env(repo_root))
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
