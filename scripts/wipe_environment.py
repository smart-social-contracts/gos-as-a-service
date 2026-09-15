#!/usr/bin/env python3
"""Wipe all canisters in a GaaS environment by reinstalling a minimal blank WASM.

Preserves canister IDs and cycles; clears installed code and canister state.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_DFX_ENV = {
    "TERM": "xterm",
    "NO_COLOR": "1",
    "DFX_WARNING": "-mainnet_plaintext_identity",
}
_MODULE_HASH_RE = re.compile(r"module\s*hash:\s*(0x[0-9a-f]+|none)", re.I)


class DfxError(RuntimeError):
    pass


@dataclass(frozen=True)
class CanisterStatus:
    canister_id: str
    status: str
    raw: str


def _run_dfx(args: list[str]) -> str:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            env={**os.environ, **_DFX_ENV},
            check=False,
        )
    except FileNotFoundError as exc:
        raise DfxError("dfx executable not found; install DFINITY SDK") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise DfxError(
            f"dfx command failed (exit {result.returncode}): {' '.join(args)}\n{detail[-1500:]}"
        )
    return result.stdout


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


def canister_status(canister_id: str, network: str, *, identity: str) -> CanisterStatus:
    raw = _run_dfx(
        ["dfx", "canister", "--network", network, "status", canister_id, "--identity", identity]
    ).strip()
    status = "unknown"
    for line in raw.splitlines():
        if line.lower().startswith("status:"):
            status = line.split(":", 1)[1].strip().lower()
            break
    return CanisterStatus(canister_id=canister_id, status=status, raw=raw)


def install_wasm(canister_id: str, wasm_path: str, network: str, mode: str, *, identity: str) -> None:
    _run_dfx(
        [
            "dfx", "canister", "--network", network, "install", canister_id,
            "--wasm", wasm_path, f"--mode={mode}", "--identity", identity, "--yes",
        ]
    )


# Minimal valid WASM module: WAT `(module)` -> 8 bytes.
BLANK_WAT = "(module)"
BLANK_WASM_B64 = "AGFzbQEAAAA="
# SHA-256 of the WASM bytes; matches `dfx canister status` module hash after install.
KNOWN_BLANK_WASM_SHA256 = (
    "93a44bbb96c751218e4c00d479e4c14358122a389acca16205b1e4d0dc5f9476"
)
KNOWN_BLANK_MODULE_HASH = f"0x{KNOWN_BLANK_WASM_SHA256}"


@dataclass(frozen=True)
class CanisterInventoryRow:
    name: str
    canister_id: str
    status: str
    module_hash: str | None


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _compile_blank_wat() -> bytes | None:
    wat2wasm = shutil.which("wat2wasm")
    if not wat2wasm:
        return None
    with tempfile.TemporaryDirectory(prefix="gaas-blank-wat-") as tmp:
        wat_path = Path(tmp) / "blank.wat"
        wasm_path = Path(tmp) / "blank.wasm"
        wat_path.write_text(BLANK_WAT + "\n", encoding="utf-8")
        subprocess.run(
            [wat2wasm, str(wat_path), "-o", str(wasm_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return wasm_path.read_bytes()


def materialize_blank_wasm() -> tuple[Path, str]:
    """Return path to blank WASM and its expected module hash; fail if not reproducible."""
    embedded = base64.b64decode(BLANK_WASM_B64)
    embedded_hash = _sha256_hex(embedded)
    if embedded_hash != KNOWN_BLANK_WASM_SHA256:
        raise SystemExit(
            "embedded blank WASM SHA-256 mismatch: "
            f"expected {KNOWN_BLANK_WASM_SHA256}, got {embedded_hash}"
        )

    compiled = _compile_blank_wat()
    if compiled is not None:
        compiled_hash = _sha256_hex(compiled)
        if compiled_hash != KNOWN_BLANK_WASM_SHA256:
            raise SystemExit(
                "wat2wasm blank module SHA-256 mismatch: "
                f"expected {KNOWN_BLANK_WASM_SHA256}, got {compiled_hash}"
            )
        if compiled != embedded:
            raise SystemExit(
                "wat2wasm output differs from embedded blank WASM bytes "
                f"(hashes match at {KNOWN_BLANK_WASM_SHA256})"
            )

    handle = tempfile.NamedTemporaryFile(
        prefix="gaas-blank-",
        suffix=".wasm",
        delete=False,
    )
    handle.write(embedded)
    handle.flush()
    handle.close()
    return Path(handle.name), KNOWN_BLANK_MODULE_HASH


def load_canisters(descriptor_path: Path, only: tuple[str, ...]) -> dict[str, str]:
    payload = json.loads(descriptor_path.read_text(encoding="utf-8"))
    canisters = {
        str(name): str(cid)
        for name, cid in (payload.get("canisters") or {}).items()
        if cid
    }
    if not canisters:
        raise SystemExit(f"{descriptor_path}: descriptor has no canisters map entries")

    if only:
        unknown = set(only) - set(canisters)
        if unknown:
            raise SystemExit(
                f"unknown --only name(s): {', '.join(sorted(unknown))}; "
                f"known: {', '.join(sorted(canisters))}"
            )
        canisters = {name: canisters[name] for name in only}

    return canisters


def collect_inventory(
    canisters: dict[str, str],
    *,
    network: str,
    identity: str,
) -> list[CanisterInventoryRow]:
    rows: list[CanisterInventoryRow] = []
    for name, canister_id in canisters.items():
        try:
            status = canister_status(canister_id, network, identity=identity)
        except DfxError as exc:
            raise SystemExit(
                f"failed to read status for {name} ({canister_id}): {exc}"
            ) from exc
        rows.append(
            CanisterInventoryRow(
                name=name,
                canister_id=canister_id,
                status=status.status,
                module_hash=parse_module_hash(status.raw),
            )
        )
    return rows


def print_inventory_table(
    rows: list[CanisterInventoryRow],
    *,
    descriptor_path: Path,
    network: str,
    identity: str,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"GaaS environment wipe — inventory ({now})")
    print(f"  descriptor: {descriptor_path}")
    print(f"  network:    {network}")
    print(f"  identity:   {identity}")
    print()
    print(f"{'Name':<28} {'Canister ID':<28} {'Status':<10} Module Hash")
    print("-" * 100)
    for row in rows:
        module_hash = row.module_hash or "(none)"
        print(
            f"{row.name:<28} {row.canister_id:<28} {row.status:<10} {module_hash}"
        )
    print()


def print_wipe_plan(
    rows: list[CanisterInventoryRow],
    *,
    network: str,
    identity: str,
    blank_hash: str,
    wasm_path: Path,
) -> None:
    print("Wipe plan (no changes — dry run):")
    for row in rows:
        print(
            f"  dfx canister --network {network} install {row.canister_id} "
            f"--mode reinstall --wasm {wasm_path} --yes --identity {identity}"
        )
    print()
    print(f"Post-wipe expected module hash for all canisters: {blank_hash}")


def confirm_wipe(canister_count: int, *, network: str) -> None:
    prompt = (
        f"Reinstall blank WASM on {canister_count} canister(s) on network "
        f"{network!r}? This DESTROYS all canister state. Type 'yes' to continue: "
    )
    answer = input(prompt).strip().lower()
    if answer != "yes":
        raise SystemExit("aborted")


def wipe_canisters(
    rows: list[CanisterInventoryRow],
    *,
    network: str,
    identity: str,
    wasm_path: Path,
    yes: bool,
) -> None:
    if not yes:
        confirm_wipe(len(rows), network=network)

    for row in rows:
        print(f"Wiping {row.name} ({row.canister_id})...")
        install_wasm(
            row.canister_id,
            str(wasm_path),
            network,
            "reinstall",
            identity=identity,
        )


def verify_wipe(
    rows: list[CanisterInventoryRow],
    *,
    network: str,
    identity: str,
    expected_hash: str,
) -> bool:
    print()
    print("Verification:")
    all_ok = True
    for row in rows:
        status = canister_status(row.canister_id, network, identity=identity)
        actual = parse_module_hash(status.raw)
        ok = actual == expected_hash
        all_ok = all_ok and ok
        verdict = "PASS" if ok else "FAIL"
        print(
            f"  [{verdict}] {row.name} ({row.canister_id}): "
            f"{actual or '(none)'} (expected {expected_hash})"
        )
    print()
    if all_ok:
        print("Final verdict: PASS — all canisters report blank module hash.")
    else:
        print("Final verdict: FAIL — one or more canisters did not match blank hash.")
    return all_ok


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Wipe all canisters listed in a GaaS environment descriptor by "
            "reinstalling a minimal blank WASM (preserves canister IDs)."
        ),
    )
    parser.add_argument(
        "descriptor",
        type=Path,
        help="Path to a JSON inventory of canisters to wipe (name → id)",
    )
    parser.add_argument(
        "--network",
        default="ic",
        help="dfx network (default: ic)",
    )
    parser.add_argument(
        "--identity",
        default="deployer",
        help="dfx identity (default: deployer)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print inventory and wipe plan only; make no changes",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip interactive confirmation",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="NAME",
        help="Wipe only this canister name (repeatable)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    descriptor_path = args.descriptor.resolve()
    if not descriptor_path.is_file():
        raise SystemExit(f"descriptor not found: {descriptor_path}")

    only = tuple(args.only)
    canisters = load_canisters(descriptor_path, only)
    wasm_path, blank_hash = materialize_blank_wasm()

    try:
        rows = collect_inventory(
            canisters,
            network=args.network,
            identity=args.identity,
        )
        print_inventory_table(
            rows,
            descriptor_path=descriptor_path,
            network=args.network,
            identity=args.identity,
        )

        if args.dry_run:
            print_wipe_plan(
                rows,
                network=args.network,
                identity=args.identity,
                blank_hash=blank_hash,
                wasm_path=wasm_path,
            )
            return 0

        wipe_canisters(
            rows,
            network=args.network,
            identity=args.identity,
            wasm_path=wasm_path,
            yes=args.yes,
        )
        ok = verify_wipe(
            rows,
            network=args.network,
            identity=args.identity,
            expected_hash=blank_hash,
        )
        return 0 if ok else 1
    finally:
        try:
            wasm_path.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
