"""Subprocess wrapper around dfx."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gaas.runlog import get_run_log

from gaas.known import DEFAULT_CYCLES_PER_CANISTER
from gaas.runlog import get_run_log

InstallMode = Literal["install", "reinstall", "upgrade"]

_DFX_ENV = {
    "TERM": "xterm",
    "NO_COLOR": "1",
    "DFX_WARNING": "-mainnet_plaintext_identity",
}

_CANISTER_ID_OUTPUT_RE = re.compile(
    r"([a-z0-9]{5}(?:-[a-z0-9]{5}){3,10}-[a-z0-9]{3})"
)
_MODULE_HASH_NONE_RE = re.compile(r"module\s*hash:\s*none", re.I)
_MODULE_HASH_RE = re.compile(r"module\s*hash:\s*(0x[0-9a-f]+|none)", re.I)
_CONTROLLERS_RE = re.compile(r"controllers:\s*(.+)", re.I)

_CERTIFIED_ASSETS_WASM_URL = (
    "https://github.com/smart-social-contracts/certified-assets"
    "/releases/download/v0.3.0/assetstorage.wasm.gz"
)

_ASSET_DEPLOY_ATTEMPTS = 3
_ASSET_DEPLOY_RETRY_DELAY_S = 5
_TRANSIENT_ASSET_SYNC_RE = re.compile(r"IC0536|Failed to list assets", re.I)


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


CANISTER_DELETE_FORBIDDEN = (
    "dfx canister delete burns leftover cycles; use Casals drain-then-delete "
    "or gaas new --destroy-except-realm-registry-frontend instead"
)


def reject_canister_delete(args: list[str]) -> None:
    """Refuse raw `dfx canister delete` — it burns leftover cycles."""
    for index, arg in enumerate(args):
        if arg == "canister" and index + 1 < len(args) and args[index + 1] == "delete":
            raise DfxError(
                CANISTER_DELETE_FORBIDDEN,
                command=args,
                stderr=CANISTER_DELETE_FORBIDDEN,
            )


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
    env_extra: dict[str, str] | None = None,
    allow_canister_delete: bool = False,
) -> subprocess.CompletedProcess[str]:
    if not allow_canister_delete:
        reject_canister_delete(args)
    env = os.environ.copy()
    env.update(_DFX_ENV)
    if env_extra:
        env.update(env_extra)
    # Some operator hosts wrap `dfx` and require --run-deprecated. Stock dfx
    # (0.30+) rejects that flag. Try with it, then retry without.
    original_args = list(args)
    injected = False
    if args and args[0] == "dfx" and "--run-deprecated" not in args:
        args = ["dfx", "--run-deprecated", *args[1:]]
        injected = True

    def _invoke(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(cwd) if cwd else None,
            check=False,
            timeout=timeout,
        )

    try:
        result = _invoke(args)
    except FileNotFoundError as exc:
        raise DfxError(
            "dfx executable not found; install DFINITY SDK",
            command=args,
            stderr=str(exc),
        ) from exc
    if (
        injected
        and result.returncode != 0
        and "unexpected argument '--run-deprecated'" in f"{result.stderr}\n{result.stdout}"
    ):
        args = original_args
        try:
            result = _invoke(args)
        except FileNotFoundError as exc:
            raise DfxError(
                "dfx executable not found; install DFINITY SDK",
                command=args,
                stderr=str(exc),
            ) from exc

    run_log = get_run_log()
    if run_log is not None:
        run_log.log_command(args, cwd=cwd)
        if result.stdout:
            run_log.log_output(result.stdout)
        if result.stderr:
            run_log.log_output(result.stderr)

    if check and result.returncode != 0:
        message = f"dfx command failed (exit {result.returncode}): {' '.join(args)}"
        detail = result.stderr.strip() or result.stdout.strip()
        if detail:
            message += f"\n{detail[-1500:]}"
        raise DfxError(
            message,
            command=args,
            stderr=result.stderr.strip(),
            stdout=result.stdout.strip(),
        )
    return result


_CANDID_ESCAPE_RE = re.compile(r"\\(?:([0-9a-fA-F]{2})|(.))")

_CANDID_NAMED_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "\\": "\\"}


def _decode_candid_text(text: str) -> str:
    """Decode Candid text escapes in a single left-to-right pass.

    Sequential str.replace calls are order-dependent and corrupt payloads whose
    JSON contains escaped backslashes (e.g. ``C:\\new`` arrives as ``\\\\\\\\n``:
    replacing ``\\n`` first eats the final backslash of the quadruple).
    """
    out: list[str] = []
    hexbuf = bytearray()
    pos = 0

    def flush_hex() -> None:
        nonlocal hexbuf
        if hexbuf:
            out.append(hexbuf.decode("utf-8", errors="replace"))
            hexbuf = bytearray()

    for match in _CANDID_ESCAPE_RE.finditer(text):
        if match.start() > pos:
            flush_hex()
            out.append(text[pos : match.start()])
        hex_digits, named = match.groups()
        if hex_digits is not None:
            hexbuf.append(int(hex_digits, 16))
        else:
            flush_hex()
            out.append(_CANDID_NAMED_ESCAPES.get(named, named))
        pos = match.end()
    flush_hex()
    out.append(text[pos:])
    return "".join(out)


def _parse_candid_string(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1].strip()
    if raw.endswith(","):
        raw = raw[:-1].strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    return _decode_candid_text(raw)


def parse_controllers(status_raw: str) -> tuple[str, ...]:
    for line in status_raw.splitlines():
        match = _CONTROLLERS_RE.search(line)
        if match:
            return tuple(_CANISTER_ID_OUTPUT_RE.findall(match.group(1)))
    return ()


def parse_module_hash(status_raw: str) -> str | None:
    """Return module hash from `dfx canister status` output, or None if absent."""
    for line in status_raw.splitlines():
        match = _MODULE_HASH_RE.search(line)
        if not match:
            continue
        value = match.group(1)
        if value.lower() == "none":
            return None
        return value.lower()
    return None


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
    return parse_cycles_balance(result.stdout)


def parse_cycles_balance(text: str) -> int | None:
    """Parse `dfx cycles balance` output like '0.281 TC (trillion cycles).'

    dfx prints either a scaled form ('3.10 TC (trillion cycles)') or a raw
    count ('3_072_815_616 cycles'); both must scale to an integer cycle count.
    """
    match = re.search(r"([\d_,]+(?:\.\d+)?)\s*TC\b", text, re.I)
    if match:
        value = float(match.group(1).replace(",", "").replace("_", ""))
        return int(value * 1_000_000_000_000)
    match = re.search(r"([\d_,]+(?:\.\d+)?)\s*cycles?\b", text, re.I)
    if match:
        value = match.group(1).replace(",", "").replace("_", "")
        return int(float(value))
    return None


def parse_canister_cycles_balance(status_raw: str) -> int | None:
    """Extract cycles balance from `dfx canister status` output."""
    for line in status_raw.splitlines():
        if line.lower().startswith("balance:"):
            return parse_cycles_balance(line)
    return parse_cycles_balance(status_raw)


def canister_cycles_balance(
    canister_id: str, network: str, *, identity: str | None = None
) -> int | None:
    status = canister_status(canister_id, network, identity=identity)
    return parse_canister_cycles_balance(status.raw)


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
    cwd: str | Path | None = None,
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
    result = _run(args, check=True, cwd=cwd)
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
        "casals_backend",
        "--no-wallet",
    ]
    if identity:
        args.extend(["--identity", identity])
    result = _run(args, check=True)
    return _parse_created_canister_id(result)


def update_canister_settings(
    canister_id: str,
    controllers: list[str],
    network: str,
    *,
    identity: str | None = None,
) -> None:
    """Replace the IC controller set for a canister."""
    if not controllers:
        raise DfxError(
            "update_canister_settings requires at least one controller",
            command=[],
            stderr="empty controllers",
        )
    args = [
        "dfx",
        "canister",
        "--network",
        network,
        "update-settings",
        canister_id,
    ]
    if identity:
        args.extend(["--identity", identity])
    for controller in controllers:
        args.extend(["--set-controller", controller])
    _run(args, check=True)


def add_canister_controller(
    canister_id: str,
    controller: str,
    network: str,
    *,
    identity: str | None = None,
) -> None:
    """Add a controller without replacing the existing set."""
    controller = (controller or "").strip()
    if not controller:
        raise DfxError(
            "add_canister_controller requires a controller principal",
            command=[],
            stderr="empty controller",
        )
    args = [
        "dfx",
        "canister",
        "--network",
        network,
        "update-settings",
        canister_id,
    ]
    if identity:
        args.extend(["--identity", identity])
    args.extend(["--add-controller", controller])
    _run(args, check=True)


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


def build_canister(
    name: str,
    network: str,
    *,
    cwd: Path,
    env_extra: dict[str, str] | None = None,
) -> None:
    _run(
        ["dfx", "build", name, "--network", network],
        check=True,
        cwd=cwd,
        env_extra=env_extra,
    )


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
    extra_network_ids: dict[str, str] | None = None,
) -> None:
    """Deploy an assets canister by temporarily mapping canister_ids.json.

    ``extra_network_ids`` are written under ``network`` for the duration of
    the deploy so the certified-assets plugin bakes a complete ``ic_env``
    cookie. Without them, ``dfx deploy --network ic`` only sees the
    frontend ID and keeps a stale backend principal in Set-Cookie.
    """
    ids_path = repo_root / "canister_ids.json"
    backup: str | None = None
    if ids_path.is_file():
        backup = ids_path.read_text(encoding="utf-8")
    data: dict[str, dict[str, str]] = {}
    if backup:
        data = json.loads(backup)
    for name, extra_id in (extra_network_ids or {}).items():
        cid = (extra_id or "").strip()
        if not name or not cid:
            continue
        extra_entry = data.setdefault(name, {})
        extra_entry[network] = cid
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
        # Right after install_code, the asset sync's `list` query can land on a
        # replica still serving the previous wasm -> spurious IC0536. The wasm
        # install is already done by then, so retrying is cheap and converges.
        for attempt in range(1, _ASSET_DEPLOY_ATTEMPTS + 1):
            try:
                _run(args, check=True, cwd=repo_root)
                break
            except DfxError as exc:
                if attempt == _ASSET_DEPLOY_ATTEMPTS or not _TRANSIENT_ASSET_SYNC_RE.search(
                    exc.stderr + exc.stdout
                ):
                    raise
                time.sleep(_ASSET_DEPLOY_RETRY_DELAY_S)
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


def is_canister_not_found_error(exc: BaseException | str) -> bool:
    text = str(exc)
    return "IC0301" in text or "not found" in text.lower()


def delete_canister(*_args: object, **_kwargs: object) -> None:
    raise DfxError(
        CANISTER_DELETE_FORBIDDEN,
        command=["dfx", "canister", "delete"],
        stderr=CANISTER_DELETE_FORBIDDEN,
    )


def delete_dust_canister(
    canister_id: str,
    network: str,
    *,
    identity: str | None = None,
    max_cycles: int = 500_000_000_000,
) -> None:
    """Delete a canister only when its balance is at or below ``max_cycles``."""
    status = canister_status(canister_id, network, identity=identity)
    balance = parse_canister_cycles_balance(status.raw)
    if balance is None or balance > max_cycles:
        raise DfxError(
            f"refusing canister delete: balance {balance} exceeds dust limit {max_cycles}",
            command=["dfx", "canister", "delete", canister_id],
            stderr=f"balance {balance}",
        )
    args = [
        "dfx",
        "canister",
        "--network",
        network,
        "delete",
        canister_id,
        "--yes",
        "--no-withdrawal",
    ]
    if identity:
        args.extend(["--identity", identity])
    _run(args, allow_canister_delete=True)


def get_wallet(network: str, *, identity: str | None = None) -> str:
    args = ["dfx", "identity", "get-wallet", "--network", network]
    if identity:
        args.extend(["--identity", identity])
    result = _run(args, check=True)
    wallet = result.stdout.strip()
    if not wallet:
        raise DfxError(
            "dfx identity get-wallet returned empty output",
            command=args,
            stderr=result.stderr,
            stdout=result.stdout,
        )
    return wallet


EPHEMERAL_HOLDING_CYCLES = 1_000_000_000_000  # 1T; IC create fee is 0.5T


def create_ephemeral_canister(
    network: str,
    *,
    identity: str | None = None,
    with_cycles: int = EPHEMERAL_HOLDING_CYCLES,
) -> str:
    """Allocate a cycles-ledger canister for treasury evacuation when no dfx wallet exists.

    ``gaas new --destroy-except-realm-registry-frontend`` then refunds this
    canister so the cycles land on the identity's cycles ledger (the same
    account ``create --no-wallet`` spends from).
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "empty.did").write_text("service : {}\n", encoding="utf-8")
        (root / "empty.wasm").write_bytes(b"\x00asm")
        (root / "dfx.json").write_text(
            json.dumps(
                {
                    "canisters": {
                        "gaas_cycles_holding": {
                            "type": "custom",
                            "candid": "empty.did",
                            "wasm": "empty.wasm",
                        }
                    },
                    "networks": {
                        "ic": {
                            "providers": ["https://icp0.io"],
                            "type": "persistent",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return create_canister(
            "gaas_cycles_holding",
            network,
            identity=identity,
            with_cycles=with_cycles,
            cwd=root,
        )


def refund_canister_to_ledger(
    canister_id: str,
    network: str,
    *,
    identity: str | None = None,
) -> None:
    """Delete a canister so leftover cycles return to the identity's cycles ledger.

    Used only for the ephemeral holding canister created when ``get_wallet``
    is unavailable. Never use this on DNS-mapped frontends.
    """
    args = [
        "dfx",
        "canister",
        "--network",
        network,
        "delete",
        canister_id,
        "--yes",
    ]
    if identity:
        args.extend(["--identity", identity])
    _run(args, allow_canister_delete=True)
