"""Bootstrap Casals conductor canisters via the Casals CLI."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from gaas.descriptor import Descriptor
from gaas.platform import require_casals_checkout

CASALS_BOOTSTRAP_NAMES: tuple[str, ...] = (
    "casals_backend",
    "casals_frontend",
    "casals_file_registry",
)

_GOS_TO_CASALS_ID_KEYS: dict[str, str] = {
    "casals_backend": "casals_backend",
    "casals_frontend": "casals_frontend",
    "casals_file_registry": "ic_file_registry",
}

_CASALS_TO_GOS_ID_KEYS: dict[str, str] = {
    "casals_backend": "casals_backend",
    "casals_frontend": "casals_frontend",
    "ic_file_registry": "casals_file_registry",
}


def casals_env(network: str) -> str:
    if (network or "").strip().lower() in ("local", "localhost"):
        return "local"
    return "ic"


def ids_file_payload(descriptor: Descriptor) -> dict[str, str]:
    payload: dict[str, str] = {}
    for gos_name in CASALS_BOOTSTRAP_NAMES:
        cid = (descriptor.canisters.get(gos_name) or "").strip()
        if cid:
            payload[_GOS_TO_CASALS_ID_KEYS[gos_name]] = cid
    return payload


def _apply_canisters_to_descriptor(
    descriptor: Descriptor, canisters: dict[str, str]
) -> None:
    for casals_key, cid in canisters.items():
        gos_name = _CASALS_TO_GOS_ID_KEYS.get(casals_key)
        if gos_name and isinstance(cid, str) and cid.strip():
            descriptor.set_canister_id(gos_name, cid.strip())


def run_casals_new(
    descriptor: Descriptor,
    *,
    network: str,
    identity: str | None,
    casals_src: Path | None,
    yes: bool = True,
    force_create: bool = False,
) -> dict:
    checkout = require_casals_checkout(casals_src)
    env = casals_env(network)

    argv: list[str] = [
        sys.executable,
        str(checkout / "scripts" / "casals.py"),
        "-e",
        env,
        "new",
    ]
    if yes:
        argv.append("-y")
    argv.append("--no-seed")
    if identity:
        argv.extend(["--identity", identity])

    existing = {} if force_create else ids_file_payload(descriptor)
    ids_path: Path | None = None
    if existing:
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".ids.json",
            delete=False,
            encoding="utf-8",
        )
        json.dump(existing, tmp)
        tmp.close()
        ids_path = Path(tmp.name)
        argv.append(str(ids_path))

    try:
        result = subprocess.run(
            argv,
            cwd=checkout,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(
                f"casals new failed (exit {result.returncode}): {stderr}"
            )

        stdout = result.stdout.strip()
        if not stdout:
            raise RuntimeError("casals new produced no JSON on stdout")

        parsed = json.loads(stdout)
        if not parsed.get("ok"):
            raise RuntimeError(
                f"casals new returned ok=false: {parsed.get('error', parsed)}"
            )
        if force_create and parsed.get("mode") == "upgrade":
            raise RuntimeError(
                "casals new upgraded an existing conductor; "
                "destroy-rebuild requires a fresh create"
            )

        canisters = parsed.get("canisters") or {}
        if isinstance(canisters, dict):
            _apply_canisters_to_descriptor(descriptor, canisters)

        return parsed
    finally:
        if ids_path is not None:
            ids_path.unlink(missing_ok=True)


def run_casals_sheet_deploy(
    sheet: dict | Path,
    *,
    network: str,
    identity: str | None,
    casals_src: Path | None,
    canister: str,
) -> dict:
    """Run ``casals sheet deploy`` against a conductor canister."""
    checkout = require_casals_checkout(casals_src)
    env = casals_env(network)

    sheet_path: Path | None = None
    tmp_path: Path | None = None
    if isinstance(sheet, dict):
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".sheet.json",
            delete=False,
            encoding="utf-8",
        )
        json.dump(sheet, tmp)
        tmp.close()
        tmp_path = Path(tmp.name)
        sheet_path = tmp_path
    else:
        sheet_path = Path(sheet)

    argv: list[str] = [
        sys.executable,
        str(checkout / "scripts" / "casals.py"),
        "-e",
        env,
        "--canister",
        canister,
        "sheet",
        "deploy",
        str(sheet_path),
    ]
    if identity:
        argv.extend(["--identity", identity])

    try:
        result = subprocess.run(
            argv,
            cwd=checkout,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(
                f"casals sheet deploy failed (exit {result.returncode}): {stderr}"
            )

        stdout = result.stdout.strip()
        if not stdout:
            raise RuntimeError("casals sheet deploy produced no JSON on stdout")

        parsed = json.loads(stdout)
        if isinstance(parsed, dict) and parsed.get("ok") is False:
            raise RuntimeError(
                f"casals sheet deploy returned ok=false: "
                f"{parsed.get('error', parsed)}"
            )
        return parsed
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
