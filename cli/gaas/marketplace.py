"""Build and wire the Realms marketplace backend/frontend from a realms checkout."""

from __future__ import annotations

import gzip
import os
import shutil
from pathlib import Path

from gaas import dfx
from gaas.codex_seed import resolve_realms_checkout
from gaas.descriptor import Descriptor
from gaas.runlog import run_subprocess
from gaas.source_build import ensure_basilisk_python

REALMS_GOS_ID = "realms-gos"
MARKETPLACE_FRONTEND_DIST = "marketplace_frontend_dist"
_BACKEND_MAIN = Path("src") / "marketplace_backend" / "main.py"
_BACKEND_DID = Path("src") / "marketplace_backend" / "marketplace_backend.did"
_FRONTEND_DIR = Path("src") / "marketplace_frontend"


class MarketplaceError(RuntimeError):
    pass


def find_realms_root(
    descriptor: Descriptor,
    *,
    gos_repo_root: Path,
    work_dir: Path,
) -> Path:
    """Resolve a Realms checkout: REALMS_SRC, sibling ``realms/``, then clone."""
    env = (os.environ.get("REALMS_SRC") or "").strip()
    if env:
        root = Path(env).expanduser().resolve()
        if not (root / _BACKEND_MAIN).is_file():
            raise MarketplaceError(
                f"REALMS_SRC={env} has no {_BACKEND_MAIN}"
            )
        return root

    sibling = gos_repo_root.parent / "realms"
    if (sibling / _BACKEND_MAIN).is_file():
        return sibling.resolve()

    entry = next(
        (item for item in descriptor.gos if item.implementation == REALMS_GOS_ID),
        None,
    )
    if entry is None:
        raise MarketplaceError(
            "no realms-gos entry in the descriptor and no sibling realms checkout; "
            "set REALMS_SRC or add a realms-gos GOS entry"
        )
    return resolve_realms_checkout(entry.release_repo, entry.version, work_dir)


def _gzip_wasm(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix == ".gz" or src.name.endswith(".wasm.gz"):
        shutil.copy2(src, dest)
        return dest
    with src.open("rb") as raw, gzip.open(dest, "wb") as gz:
        shutil.copyfileobj(raw, gz)
    return dest


def build_marketplace_backend_wasm(
    descriptor: Descriptor,
    *,
    gos_repo_root: Path,
    work_dir: Path,
) -> Path:
    """Basilisk-build marketplace_backend from a Realms checkout."""
    realms = find_realms_root(
        descriptor, gos_repo_root=gos_repo_root, work_dir=work_dir
    )
    main_py = realms / _BACKEND_MAIN
    did = realms / _BACKEND_DID
    if not main_py.is_file():
        raise MarketplaceError(f"missing marketplace backend source: {main_py}")
    py = ensure_basilisk_python(gos_repo_root)
    env = {**os.environ}
    if did.is_file():
        env["CANISTER_CANDID_PATH"] = str(did)
    run_subprocess(
        [str(py), "-m", "basilisk", "marketplace_backend", str(main_py)],
        cwd=realms,
        env=env,
        check=True,
        label="basilisk marketplace_backend",
    )
    wasm = realms / ".basilisk" / "marketplace_backend" / "marketplace_backend.wasm"
    if not wasm.is_file():
        raise MarketplaceError(f"basilisk did not produce {wasm}")
    return _gzip_wasm(wasm, work_dir / "marketplace_backend.wasm.gz")


def build_marketplace_frontend(
    descriptor: Descriptor,
    *,
    gos_repo_root: Path,
    work_dir: Path,
    marketplace_backend_id: str,
    file_registry_id: str,
) -> Path:
    """Vite-build the marketplace SPA (skip dfx generate) into repo dist."""
    realms = find_realms_root(
        descriptor, gos_repo_root=gos_repo_root, work_dir=work_dir
    )
    frontend = realms / _FRONTEND_DIR
    if not frontend.is_dir():
        raise MarketplaceError(f"missing marketplace frontend: {frontend}")

    run_subprocess(
        ["npm", "install", "--legacy-peer-deps"],
        cwd=realms,
        check=True,
        label="npm install (realms)",
    )
    env = {
        **os.environ,
        "CANISTER_ID_MARKETPLACE_BACKEND": marketplace_backend_id,
        "VITE_CANISTER_ID_MARKETPLACE_BACKEND": marketplace_backend_id,
        "VITE_MARKETPLACE_CANISTER_ID": marketplace_backend_id,
        "CANISTER_ID_FILE_REGISTRY": file_registry_id,
        "VITE_CANISTER_ID_FILE_REGISTRY": file_registry_id,
        "DFX_NETWORK": "ic",
    }
    run_subprocess(
        ["npx", "vite", "build"],
        cwd=frontend,
        env=env,
        check=True,
        label="vite build marketplace_frontend",
    )
    src_dist = frontend / "dist"
    if not src_dist.is_dir() or not any(src_dist.iterdir()):
        raise MarketplaceError(f"marketplace frontend build produced empty {src_dist}")

    dest = gos_repo_root / MARKETPLACE_FRONTEND_DIST
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src_dist, dest)
    return dest


def configure_marketplace_backend(
    descriptor: Descriptor,
    *,
    network: str,
    identity: str,
) -> None:
    """Point marketplace_backend at file_registry and optional billing principal."""
    marketplace_id = (descriptor.canisters.get("marketplace_backend") or "").strip()
    file_registry_id = (descriptor.canisters.get("file_registry") or "").strip()
    if not marketplace_id or not file_registry_id:
        return
    dfx.canister_call(
        marketplace_id,
        "set_file_registry_canister_id",
        dfx.candid_text_arg(file_registry_id),
        network,
        identity=identity,
    )
    billing = (descriptor.services.billing_service_principal or "").strip()
    if billing:
        dfx.canister_call(
            marketplace_id,
            "set_billing_service_principal",
            dfx.candid_text_arg(billing),
            network,
            identity=identity,
        )
