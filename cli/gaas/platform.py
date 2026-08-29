"""Resolve platform and Casals WASM artifacts (local build vs GitHub release)."""

from __future__ import annotations

import gzip
import os
import shutil
import sys
import tarfile
import urllib.parse
from pathlib import Path

import requests

from gaas.artifacts import ArtifactError, fetch_release_assets
from gaas.ic_assets import merge_casals_ic_assets, url_to_origin
from gaas.runlog import run_subprocess
from gaas.known import (
    CASALS_BACKEND_WASM_ASSET,
    CASALS_FILE_REGISTRY_WASM_ASSET,
    CASALS_FILE_REGISTRY_WASM_ASSETS,
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
    run_subprocess([sys.executable, "-m", "venv", str(venv)], check=True, cwd=casals_root)
    pip = venv / "bin" / "pip"
    run_subprocess([str(pip), "install", "-q", "--upgrade", "pip"], check=True)
    run_subprocess(
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
    run_subprocess(
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
    run_subprocess(["npm", "ci"], cwd=frontend_dir, check=True, env=env)
    run_subprocess(["npm", "run", "build"], cwd=frontend_dir, check=True, env=env)
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


def _casals_frontend_cache_usable(cached: Path) -> bool:
    """Reject a leftover cookie-only .ic-assets.json5 from older gaas injects."""
    if not cached.is_dir() or not any(cached.iterdir()):
        return False
    assets = cached / ".ic-assets.json5"
    if not assets.is_file():
        return True
    return "Content-Security-Policy" in assets.read_text(encoding="utf-8")


def _inject_casals_ic_env_assets(
    dist_dir: Path,
    conductor_id: str,
    frontend_id: str = "",
    monitor_url: str = "",
) -> None:
    """Merge ic_env cookie (and optional monitor connect-src) into .ic-assets.json5.

    Must not overwrite Casals' CSP / cache / Permissions-Policy rules. Local
    builds bake VITE_CANISTER_ID; the cookie is for prebuilt release tarballs.
    """
    path = dist_dir / ".ic-assets.json5"
    existing = path.read_text(encoding="utf-8") if path.is_file() else "[]"
    cookie_val = _casals_ic_env_cookie_value(conductor_id, frontend_id)
    cookie_header = f"ic_env={cookie_val}; SameSite=Lax"
    merged = merge_casals_ic_assets(
        existing, cookie_header, url_to_origin(monitor_url)
    )
    path.write_text(merged, encoding="utf-8")


def resolve_casals_frontend_dist(
    version: str,
    release_repo: str,
    dest: Path,
    *,
    casals_src: Path | None = None,
    session: requests.Session | None = None,
    conductor_canister_id: str = "",
    frontend_canister_id: str = "",
    monitor_url: str = "",
) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    cached = dest / "dist"
    if _casals_frontend_cache_usable(cached):
        dist = cached
    else:
        if cached.exists():
            shutil.rmtree(cached)
        dist = _materialize_casals_frontend_dist(
            version,
            release_repo,
            dest,
            casals_src=casals_src,
            session=session,
            conductor_canister_id=conductor_canister_id,
        )

    if conductor_canister_id:
        _inject_casals_ic_env_assets(
            dist,
            conductor_canister_id,
            frontend_canister_id,
            monitor_url=monitor_url,
        )
    return dist


def _materialize_casals_frontend_dist(
    version: str,
    release_repo: str,
    dest: Path,
    *,
    casals_src: Path | None = None,
    session: requests.Session | None = None,
    conductor_canister_id: str = "",
) -> Path:
    resolved = resolve_deploy_version(version, release_repo, session=session)
    if resolved.source_build:
        src = resolve_casals_src(casals_src)
        repo_root = src if src is not None else clone_repo(
            release_repo, dest.parent / "src-clone"
        )
        return build_casals_frontend(
            repo_root, dest, conductor_canister_id=conductor_canister_id
        )

    try:
        archive = fetch_casals_frontend_archive(
            resolved.fetch_tag or version, release_repo, dest, session=session
        )
        cached = dest / "dist"
        cached.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(cached)
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
        src = resolve_casals_src(casals_src)
        repo_root = src if src is not None else clone_repo(
            release_repo, dest.parent / "src-clone"
        )
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


def _casals_file_registry_submodule(casals_root: Path) -> Path:
    submodule = casals_root / "file_registry"
    if (submodule / "src" / "main.py").is_file() and (
        submodule / "ic_file_registry.did"
    ).is_file():
        return submodule
    raise PlatformError(
        f"Casals checkout at {casals_root} is missing the file_registry submodule; "
        "run `git submodule update --init file_registry` in the Casals repo"
    )


def build_casals_file_registry_wasm(casals_root: Path, dest: Path) -> Path:
    _casals_file_registry_submodule(casals_root)
    dest.mkdir(parents=True, exist_ok=True)
    output = dest / "ic_file_registry.wasm"
    if output.is_file():
        return output
    built = casals_root / ".basilisk" / "ic_file_registry" / "ic_file_registry.wasm"
    if built.is_file():
        shutil.copy2(built, output)
        return output
    py = _basilisk_python(casals_root)
    env = {
        **os.environ,
        "CANISTER_CANDID_PATH": str(
            casals_root / "file_registry" / "ic_file_registry.did"
        ),
    }
    run_subprocess(
        [str(py), "-m", "basilisk", "ic_file_registry", "file_registry/src/main.py"],
        cwd=casals_root,
        env=env,
        check=True,
    )
    if not built.is_file():
        raise PlatformError(f"Casals basilisk build did not produce {built}")
    shutil.copy2(built, output)
    return output


def fetch_casals_file_registry_wasm(
    version: str,
    release_repo: str,
    dest: Path,
    *,
    session: requests.Session | None = None,
) -> Path:
    resolved = resolve_deploy_version(version, release_repo, session=session)
    tag = resolved.fetch_tag or version
    assets = ["checksums.txt", *CASALS_FILE_REGISTRY_WASM_ASSETS]
    paths = fetch_release_assets(release_repo, tag, assets, dest, session=session)
    for asset_name in CASALS_FILE_REGISTRY_WASM_ASSETS:
        for path in paths:
            if path.name == asset_name:
                return _ensure_uncompressed_wasm(path)
    raise ArtifactError(
        f"no file-registry WASM asset ({', '.join(CASALS_FILE_REGISTRY_WASM_ASSETS)}) "
        f"in {release_repo} {tag}"
    )


def resolve_casals_file_registry_wasm(
    version: str,
    release_repo: str,
    work_dir: Path,
    *,
    casals_src: Path | None = None,
    session: requests.Session | None = None,
) -> Path:
    dest = work_dir / "casals_file_registry"
    dest.mkdir(parents=True, exist_ok=True)
    cached = dest / "ic_file_registry.wasm"
    if cached.is_file():
        return cached

    resolved = resolve_deploy_version(version, release_repo, session=session)
    if resolved.source_build:
        src = resolve_casals_src(casals_src)
        repo_root = src if src is not None else clone_repo(
            release_repo, dest.parent / "src-clone"
        )
        return build_casals_file_registry_wasm(repo_root, dest)

    try:
        return fetch_casals_file_registry_wasm(
            resolved.fetch_tag or version, release_repo, dest, session=session
        )
    except ArtifactError:
        src = resolve_casals_src(casals_src)
        if src is None:
            raise PlatformError(
                f"Casals release {release_repo}@{version} has no "
                f"{CASALS_FILE_REGISTRY_WASM_ASSET}; provide --casals-src, set CASALS_SRC, "
                "or place a Casals checkout with the file_registry submodule at /srv/dev/Casals"
            ) from None
        return build_casals_file_registry_wasm(src, dest)


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
    """Put a basilisk venv first on PATH so `python -m basilisk` uses it."""
    for venv_bin in (
        repo_root / ".venv-basilisk" / "bin",
        Path.home() / ".venv-basilisk" / "bin",
    ):
        if venv_bin.is_dir():
            return {"PATH": f"{venv_bin}{os.pathsep}{os.environ.get('PATH', '')}"}
    return None


def find_local_assetstorage_wasm(repo_root: Path | None = None) -> Path:
    """Locate certified-assets canister wasm (assetstorage.wasm.gz) on disk."""
    if repo_root is not None:
        dfx_ic = repo_root / ".dfx" / "ic" / "canisters"
        if dfx_ic.is_dir():
            for candidate in sorted(dfx_ic.glob("*/assetstorage.wasm.gz")):
                if candidate.is_file():
                    return candidate

    from gaas import dfx

    try:
        cache = dfx._run(["dfx", "cache", "show"], check=True).stdout.strip()
        cache_path = Path(cache) / "assetstorage.wasm.gz"
        if cache_path.is_file():
            return cache_path
    except dfx.DfxError:
        pass

    try:
        return dfx.find_assetstorage_wasm()
    except Exception as exc:
        raise PlatformError(
            "certified-assets canister wasm (assetstorage.wasm.gz) not found; "
            "deploy a platform frontend with dfx first (creates "
            ".dfx/ic/canisters/*/assetstorage.wasm.gz) or install dfx so its cache "
            "contains assetstorage.wasm.gz"
        ) from exc


def _local_backend_wasm(repo_root: Path, canister: str) -> Path:
    """Pack a Basilisk backend from this checkout without a local replica.

    ``dfx build --network local`` needs ``dfx start`` plus local canister IDs.
    Current-main deploys (``platform.version`` unset) run on operator hosts
    that often have neither. Invoke ``python -m basilisk`` directly; that is
    what ``dfx.json`` ``build`` already runs.
    """
    from gaas.runlog import run_subprocess
    from gaas.source_build import ensure_basilisk_python

    dfx_name = DFX_CANISTER_NAMES.get(canister)
    if not dfx_name:
        raise PlatformError(f"no local dfx build mapping for {canister}")
    entry = repo_root / "src" / dfx_name / "main.py"
    candid = repo_root / "src" / dfx_name / f"{dfx_name}.did"
    if not entry.is_file():
        raise PlatformError(f"missing Basilisk entry {entry}")
    repo_py = repo_root / ".venv-basilisk" / "bin" / "python"
    home_py = Path.home() / ".venv-basilisk" / "bin" / "python"
    if repo_py.is_file():
        py = repo_py
    elif home_py.is_file():
        py = home_py
    else:
        py = ensure_basilisk_python(repo_root)
    env = {
        **os.environ,
        "CANISTER_CANDID_PATH": str(candid) if candid.is_file() else os.environ.get(
            "CANISTER_CANDID_PATH", ""
        ),
        "PATH": f"{py.parent}{os.pathsep}{os.environ.get('PATH', '')}",
    }
    run_subprocess(
        [str(py), "-m", "basilisk", dfx_name, str(entry)],
        cwd=repo_root,
        env=env,
        check=True,
    )
    plain = repo_root / ".basilisk" / dfx_name / f"{dfx_name}.wasm"
    if plain.is_file():
        return plain
    gz = repo_root / ".dfx" / "local" / "canisters" / dfx_name / f"{dfx_name}.wasm.gz"
    if gz.is_file():
        return _ensure_uncompressed_wasm(gz)
    raise PlatformError(f"basilisk pack {dfx_name} did not produce WASM under {repo_root}")


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
