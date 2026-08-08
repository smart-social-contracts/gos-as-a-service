"""Subprocess wrapper around dfx."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gaas.known import DEFAULT_CYCLES_PER_CANISTER

InstallMode = Literal["install", "reinstall", "upgrade"]

_DFX_ENV = {
    "TERM": "xterm",
    "NO_COLOR": "1",
    "DFX_WARNING": "-mainnet_plaintext_identity",
}

_CANISTER_ID_OUTPUT_RE = re.compile(
    r"([a-z0-9]{5}(?:-[a-z0-9]{5}){3,10}-[a-z]{3})"
)
_CYCLES_BALANCE_RE = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*(?:TC|Trillion|T)?\s*cycles?", re.I
)
_MODULE_HASH_NONE_RE = re.compile(r"module\s*hash:\s*none", re.I)
_CONTROLLERS_RE = re.compile(r"controllers:\s*(.+)", re.I)

_CERTIFIED_ASSETS_WASM_URL = (
    "https://github.com/smart-social-contracts/certified-assets"
    "/releases/download/v0.3.0/assetstorage.wasm.gz"
)


class DfxError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        command: list[str],
        stderr: str,
        stdout: str = "",
    ) -> None:
        super().__init__(message)
        self.command = command
        self.stderr = stderr
        self.stdout = stdout


@dataclass(frozen=True)
class CanisterStatus:
    canister_id: str
    status: str
    raw: str
    controllers: tuple[str, ...] = ()
    module_hash_missing: bool = False


def _run(
    args: list[str],
    *,
    check: bool = True,
    cwd: str | Path | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(_DFX_ENV)
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(cwd) if cwd else None,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise DfxError(
            "dfx executable not found; install DFINITY SDK",
            command=args,
            stderr=str(exc),
        ) from exc

    if check and result.returncode != 0:
        raise DfxError(
            f"dfx command failed (exit {result.returncode}): {' '.join(args)}",
            command=args,
            stderr=result.stderr.strip(),
            stdout=result.stdout.strip(),
        )
    return result


def _parse_candid_string(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1].strip()
    if raw.endswith(","):
        raw = raw[:-1].strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    return raw.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")


def parse_controllers(status_raw: str) -> tuple[str, ...]:
    for line in status_raw.splitlines():
        match = _CONTROLLERS_RE.search(line)
        if match:
            return tuple(_CANISTER_ID_OUTPUT_RE.findall(match.group(1)))
    return ()


def identity_exists(name: str) -> bool:
    result = _run(["dfx", "identity", "list"], check=True)
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith(name + " ") or stripped == name:
            return True
        if stripped.endswith(f" {name}") or stripped.endswith(f" {name} *"):
            return True
        parts = stripped.split()
        if parts and parts[0] == name:
            return True
    return False


def use_identity(name: str) -> None:
    _run(["dfx", "identity", "use", name], check=True)


def get_principal(identity: str | None = None) -> str:
    args = ["dfx", "identity", "get-principal"]
    if identity:
        args.extend(["--identity", identity])
    result = _run(args, check=True)
    principal = result.stdout.strip()
    if not principal:
        raise DfxError(
            "dfx identity get-principal returned empty output",
            command=args,
            stderr=result.stderr,
            stdout=result.stdout,
        )
    return principal


def canister_status(canister_id: str, network: str, *, identity: str | None = None) -> CanisterStatus:
    args = [
        "dfx",
        "canister",
        "--network",
        network,
        "status",
        canister_id,
    ]
    if identity:
        args.extend(["--identity", identity])
    result = _run(args, check=True)
    raw = result.stdout.strip()
    status = "unknown"
    for line in raw.splitlines():
        if line.lower().startswith("status:"):
            status = line.split(":", 1)[1].strip().lower()
            break
    controllers = parse_controllers(raw)
    module_hash_missing = bool(_MODULE_HASH_NONE_RE.search(raw))
    return CanisterStatus(
        canister_id=canister_id,
        status=status,
        raw=raw,
        controllers=controllers,
        module_hash_missing=module_hash_missing,
    )


def cycles_balance(network: str, *, identity: str | None = None) -> int | None:
    args = ["dfx", "cycles", "balance", "--network", network]
    if identity:
        args.extend(["--identity", identity])
    result = _run(args, check=False)
    if result.returncode != 0:
        if network == "local":
            return None
        raise DfxError(
            f"dfx cycles balance failed on network {network}",
            command=args,
            stderr=result.stderr.strip(),
            stdout=result.stdout.strip(),
        )
    match = _CYCLES_BALANCE_RE.search(result.stdout)
    if not match:
        digits = re.sub(r"[^\d]", "", result.stdout)
        if digits:
            return int(digits)
        return None
    return int(match.group(1).replace(",", "").split(".")[0])


def ping_local() -> bool:
    result = _run(["dfx", "ping", "local"], check=False)
    return result.returncode == 0


def _parse_created_canister_id(result: subprocess.CompletedProcess[str]) -> str:
    combined = result.stdout + "\n" + result.stderr
    match = _CANISTER_ID_OUTPUT_RE.search(combined)
    if not match:
        raise DfxError(
            "could not parse canister ID from dfx output",
            command=result.args if isinstance(result.args, list) else [],
            stderr=result.stderr,
            stdout=result.stdout,
        )
    return match.group(1)


def create_canister(
    name: str,
    network: str,
    *,
    identity: str | None = None,
    with_cycles: int | None = None,
) -> str:
    args = [
        "dfx",
        "canister",
        "--network",
        network,
        "create",
        name,
        "--no-wallet",
    ]
    if identity:
        args.extend(["--identity", identity])
    if with_cycles is not None:
        args.extend(["--with-cycles", str(with_cycles)])
    result = _run(args, check=True)
    return _parse_created_canister_id(result)


def create_canister_via_ledger(
    network: str,
    *,
    identity: str | None = None,
    controller: str | None = None,
) -> str:
    if network != "ic":
        return create_canister_local(network, identity=identity, controller=controller)
    principal = controller or get_principal(identity)
    args = [
        "dfx",
        "ledger",
        "create-canister",
        principal,
        "--network",
        network,
    ]
    if identity:
        args.extend(["--identity", identity])
    args.extend(["--amount", "0.001"])
    result = _run(args, check=True)
    return _parse_created_canister_id(result)


def create_canister_local(
    network: str,
    *,
    identity: str | None = None,
    controller: str | None = None,
) -> str:
    """Create a canister on the local replica without the cycles ledger."""
    del controller  # dfx --no-wallet uses the caller identity as controller
    args = [
        "dfx",
        "canister",
        "--network",
        network,
        "create",
        "casals_conductor",
        "--no-wallet",
    ]
    if identity:
        args.extend(["--identity", identity])
    result = _run(args, check=True)
    return _parse_created_canister_id(result)


def install_wasm(
    canister_id: str,
    wasm_path: str,
    network: str,
    mode: InstallMode,
    arg: str | None = None,
    *,
    identity: str | None = None,
    yes: bool = False,
) -> None:
    args = [
        "dfx",
        "canister",
        "--network",
        network,
        "install",
        canister_id,
        "--wasm",
        wasm_path,
        f"--mode={mode}",
    ]
    if identity:
        args.extend(["--identity", identity])
    if arg is not None:
        args.extend(["--argument", arg])
    if yes:
        args.append("--yes")
    _run(args, check=True)


def canister_call(
    canister_id: str,
    method: str,
    arg: str,
    network: str,
    *,
    identity: str | None = None,
    query: bool = False,
    timeout: int = 120,
) -> str:
    cmd = ["dfx", "canister", "call"]
    if identity:
        cmd.extend(["--identity", identity])
    cmd.extend(["--network", network])
    if query:
        cmd.append("--query")

    arg_file = None
    if len(arg.encode("utf-8")) >= 100 * 1024:
        fd, arg_file = tempfile.mkstemp(prefix="gaas-dfx-arg-", suffix=".did")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(arg)
            cmd.extend([canister_id, method, "--argument-file", arg_file])
        except Exception:
            if arg_file:
                os.unlink(arg_file)
            raise
    else:
        cmd.extend([canister_id, method, arg])

    try:
        result = _run(cmd, check=True, timeout=timeout)
        return _parse_candid_string(result.stdout)
    finally:
        if arg_file:
            try:
                os.unlink(arg_file)
            except OSError:
                pass


def candid_text_arg(payload: str) -> str:
    escaped = payload.replace("\\", "\\\\").replace('"', '\\"')
    return f'("{escaped}")'


def build_canister(name: str, network: str, *, cwd: Path) -> None:
    _run(["dfx", "build", name, "--network", network], check=True, cwd=cwd)


def find_assetstorage_wasm() -> Path:
    try:
        cache = _run(["dfx", "cache", "show"], check=True).stdout.strip()
        for candidate in Path(cache).rglob("assetstorage.wasm.gz"):
            return candidate
    except DfxError:
        pass
    cache_path = Path("/tmp/gaas-assetstorage.wasm.gz")
    if not cache_path.is_file():
        import urllib.request

        urllib.request.urlretrieve(_CERTIFIED_ASSETS_WASM_URL, cache_path)
    return cache_path


def deploy_assets_canister(
    canister_name: str,
    canister_id: str,
    network: str,
    *,
    repo_root: Path,
    identity: str | None = None,
    mode: InstallMode = "reinstall",
    yes: bool = False,
) -> None:
    """Deploy an assets canister by temporarily mapping canister_ids.json."""
    ids_path = repo_root / "canister_ids.json"
    backup: str | None = None
    if ids_path.is_file():
        backup = ids_path.read_text(encoding="utf-8")
    data: dict[str, dict[str, str]] = {}
    if backup:
        data = json.loads(backup)
    entry = data.setdefault(canister_name, {})
    entry[network] = canister_id
    ids_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        args = [
            "dfx",
            "deploy",
            canister_name,
            "--network",
            network,
            f"--mode={mode}",
        ]
        if identity:
            args.extend(["--identity", identity])
        if yes:
            args.append("--yes")
        _run(args, check=True, cwd=repo_root)
    finally:
        if backup is None:
            if ids_path.is_file():
                ids_path.unlink()
        else:
            ids_path.write_text(backup, encoding="utf-8")


def top_up_canister(
    canister_id: str,
    amount: int,
    network: str,
    *,
    identity: str | None = None,
) -> None:
    args = [
        "dfx",
        "cycles",
        "top-up",
        canister_id,
        str(amount),
        "--network",
        network,
    ]
    if identity:
        args.extend(["--identity", identity])
    _run(args, check=False)


def detect_install_mode(canister_id: str, network: str, *, identity: str | None = None) -> InstallMode:
    status = canister_status(canister_id, network, identity=identity)
    if status.module_hash_missing:
        return "install"
    return "upgrade"
