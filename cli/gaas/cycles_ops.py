"""Ops-pool cycles: status, pull from a sibling Casals treasury, ensure-before-new.

``gaas new`` spends the identity's cycles ledger (or dfx wallet). Casals
treasuries hold operating float. When the ledger is short and the descriptor
lists ``cycles.pull_from``, we move only the shortfall from those treasuries
and leave ``cycles.pull_leave_tc`` on the source.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from gaas import dfx
from gaas.cycles_plan import CyclesPlan, _format_cycles, build_cycles_plan
from gaas.descriptor import Descriptor
from gaas.destroy import (
    _casals_call,
    _clear_persisted_holding,
    _resolve_cycles_destination,
)

BRIDGE_CANISTER = "gaas-cycles-bridge"
BRIDGE_SECTION = "Casals"
BRIDGE_STAND = "System"
# Dest Casals tree names used by ``ensure_platform_stand`` / sheet seed.
ORCHESTRA_TREE_NAMES = {
    "file_registry": "file-registry",
    "file_registry_frontend": "file-registry-frontend",
    "casals_file_registry": "casals-file-registry",
    "realm_installer": "realm-installer",
    "realm_registry_backend": "realm-registry-backend",
    "realm_registry_frontend": "realm-registry-frontend",
}
# Ephemeral holding create burns ~0.5T from the ledger (IC create tax) plus
# a bit of idle/call burn. Pull this much extra so preflight is not left
# a few hundred B short after a successful-looking transfer.
PULL_OVERHEAD_CYCLES = 1_000_000_000_000
# Preferred leave is ``cycles.pull_leave_tc`` (default 40 TC). A from-scratch
# recreate burns ~8 TC on install/seed that evacuation cannot return. If the
# wallet is still short after the preferred floor, take the rest down to
# this hard floor so ``gaas new`` does not stop for ``dfx cycles convert``.
# 15–20 TC left siblings unable to fund both the recreate wallet and the
# post-seed one-realm refill (installer spendable 7 TC). 8 TC still sits
# above a 2 TC autopilot min on staging/test.
PULL_HARD_LEAVE_CYCLES = 8_000_000_000_000

_AMOUNT_RE = re.compile(
    r"^\s*([\d_]+(?:\.\d+)?)\s*(t|tc|T|TC)?\s*$"
)


def parse_cycles_amount(text: str) -> int:
    """Parse ``25t`` / ``25TC`` / a raw cycle count into an integer."""
    match = _AMOUNT_RE.match(text or "")
    if not match:
        raise ValueError(f"invalid cycles amount {text!r} (use 25t or a raw count)")
    value = float(match.group(1).replace("_", ""))
    if match.group(2):
        return int(value * 1_000_000_000_000)
    return int(value)


def resolve_pull_source_paths(
    descriptor: Descriptor,
    descriptor_path: Path | None,
) -> list[Path]:
    """Resolve ``cycles.pull_from`` names/paths next to the descriptor."""
    refs = list(descriptor.cycles.pull_from)
    if not refs:
        return []
    base = (
        Path(descriptor_path).resolve().parent
        if descriptor_path
        else Path.cwd()
    )
    found: list[Path] = []
    for ref in refs:
        candidate = Path(ref).expanduser()
        if candidate.is_file():
            found.append(candidate.resolve())
            continue
        search = [
            base / f"{ref}.json",
            base / ref,
            base / "environments" / f"{ref}.json",
        ]
        hit = next((path for path in search if path.is_file()), None)
        if hit is None:
            raise RuntimeError(
                f"cycles.pull_from {ref!r} not found next to {descriptor_path}"
            )
        found.append(hit.resolve())
    return found


def _wallet_shortfall(plan: CyclesPlan) -> int:
    for item in plan.items:
        if item.label == "wallet":
            return item.shortfall
    return 0


def _ok_or_raise(parsed: dict[str, Any], method: str) -> dict[str, Any]:
    if parsed.get("ok") is False:
        raise RuntimeError(parsed.get("error") or f"Casals {method} failed")
    return parsed


def _ensure_bridge_stand(
    casals_id: str,
    *,
    network: str,
    identity: str,
) -> None:
    created = _casals_call(
        casals_id,
        "create_section",
        {"name": BRIDGE_SECTION, "description": "GaaS cycles bridge"},
        network=network,
        identity=identity,
    )
    if created.get("ok") is False and "already exists" not in str(
        created.get("error") or ""
    ):
        raise RuntimeError(created.get("error") or "create_section failed")
    stand = _casals_call(
        casals_id,
        "create_stand",
        {
            "section": BRIDGE_SECTION,
            "name": BRIDGE_STAND,
            "description": "GaaS cycles bridge",
        },
        network=network,
        identity=identity,
    )
    if stand.get("ok") is False and "already exists" not in str(
        stand.get("error") or ""
    ):
        raise RuntimeError(stand.get("error") or "create_stand failed")


def _drop_bridge(
    casals_id: str,
    dest_id: str,
    *,
    network: str,
    identity: str,
) -> None:
    """Retire the bridge tree row and evict dest from the source pool.

    Casals ``delete_canister`` only frees the pool entry. Leaving dest in
    the source pool lets staging/test recycle a live sibling canister.
    """
    dropped = _casals_call(
        casals_id,
        "delete_canister",
        {"canister": BRIDGE_CANISTER},
        network=network,
        identity=identity,
    )
    if dropped.get("ok") is False and "unknown canister" not in str(
        dropped.get("error") or ""
    ):
        raise RuntimeError(dropped.get("error") or "delete_canister failed")
    removed = _casals_call(
        casals_id,
        "pool_remove",
        {"canister_id": dest_id},
        network=network,
        identity=identity,
    )
    if removed.get("ok") is False:
        error = str(removed.get("error") or "")
        if "not in pool" not in error.lower():
            raise RuntimeError(error or "pool_remove failed")


def _register_bridge(
    casals_id: str,
    holding_id: str,
    *,
    network: str,
    identity: str,
) -> None:
    registered = _casals_call(
        casals_id,
        "register_canister",
        {
            "stand": BRIDGE_STAND,
            "name": BRIDGE_CANISTER,
            "canister_id": holding_id,
            "kind": "backend",
        },
        network=network,
        identity=identity,
    )
    if registered.get("ok") is not False:
        return
    error = str(registered.get("error") or "")
    if "already exists" not in error.lower():
        raise RuntimeError(error or "register_canister failed")
    # Drop a stale bridge row (previous pull refunded the IC canister) and retry.
    deleted = _casals_call(
        casals_id,
        "delete_canister",
        {"canister": BRIDGE_CANISTER},
        network=network,
        identity=identity,
    )
    if deleted.get("ok") is False and "unknown canister" not in str(
        deleted.get("error") or ""
    ):
        raise RuntimeError(deleted.get("error") or "delete_canister failed")
    _ok_or_raise(
        _casals_call(
            casals_id,
            "register_canister",
            {
                "stand": BRIDGE_STAND,
                "name": BRIDGE_CANISTER,
                "canister_id": holding_id,
                "kind": "backend",
            },
            network=network,
            identity=identity,
        ),
        "register_canister",
    )


def pull_from_casals_treasury(
    casals_id: str,
    amount: int,
    *,
    leave: int,
    network: str,
    identity: str,
    destination: str | None = None,
) -> int:
    """Move up to ``amount`` cycles from a Casals treasury.

    Default dest is the ops ledger (wallet or ephemeral holding). When
    ``destination`` is set, deposit onto that live canister instead — no
    holding mint, no refund. Leaves at least ``leave`` on the source.
    Returns cycles actually moved (0 if the source is already at the leave
    floor).
    """
    if amount <= 0:
        return 0
    status = dfx.canister_status(casals_id, network, identity=identity)
    balance = dfx.parse_canister_cycles_balance(status.raw)
    if balance is None:
        raise RuntimeError(f"cannot read cycles on source Casals {casals_id}")
    take = min(amount, max(0, balance - leave))
    if take <= 0:
        return 0

    dest = (destination or "").strip() or None
    ephemeral = False
    if dest:
        holding = dest
    else:
        holding, ephemeral = _resolve_cycles_destination(network, identity)
    if holding == casals_id:
        raise RuntimeError("refusing to pull cycles into the source Casals treasury")

    _ensure_bridge_stand(casals_id, network=network, identity=identity)
    _register_bridge(casals_id, holding, network=network, identity=identity)
    _ok_or_raise(
        _casals_call(
            casals_id,
            "top_up",
            {"canister": BRIDGE_CANISTER, "amount": take},
            network=network,
            identity=identity,
        ),
        "top_up",
    )

    if dest:
        _drop_bridge(casals_id, dest, network=network, identity=identity)
        return take

    if ephemeral:
        dfx.refund_canister_to_ledger(holding, network, identity=identity)
        _clear_persisted_holding()
        dropped = _casals_call(
            casals_id,
            "delete_canister",
            {"canister": BRIDGE_CANISTER},
            network=network,
            identity=identity,
        )
        if dropped.get("ok") is False and "unknown canister" not in str(
            dropped.get("error") or ""
        ):
            raise RuntimeError(dropped.get("error") or "delete_canister failed")
    return take


def _pull_sibling_surplus(
    descriptor: Descriptor,
    shortfall: int,
    *,
    network: str,
    identity: str,
    descriptor_path: Path | None,
    leftover_fn,
    destination: str | None = None,
) -> dict[str, Any]:
    """Pull ``shortfall`` from ``cycles.pull_from`` treasuries (two-pass leave).

    Ledger pulls add ``PULL_OVERHEAD_CYCLES`` (holding create tax). Direct
    ``destination`` pulls skip that overhead — dest is already live.
    """
    if shortfall <= 0 or not descriptor.cycles.pull_from:
        return {"pulled": 0, "shortfall": shortfall, "dipped": False}

    dest_casals = (descriptor.canisters.get("casals_backend") or "").strip()
    dest = (destination or "").strip() or None
    overhead = 0 if dest else PULL_OVERHEAD_CYCLES
    leave = descriptor.cycles.pull_leave_cycles()
    pulled = 0
    remaining = shortfall + overhead
    sources = list(resolve_pull_source_paths(descriptor, descriptor_path))
    leftover = shortfall
    dipped = False

    def _pull_pass(leave_cycles: int, want: int) -> int:
        got_total = 0
        left = want
        for path in sources:
            if left <= 0:
                break
            source = Descriptor.load(path)
            casals_id = (source.canisters.get("casals_backend") or "").strip()
            if not casals_id or casals_id == dest_casals:
                continue
            got = pull_from_casals_treasury(
                casals_id,
                left,
                leave=leave_cycles,
                network=network,
                identity=identity,
                destination=dest,
            )
            if got <= 0:
                continue
            got_total += got
            left -= got
        return got_total

    for _pass in range(2):
        if remaining <= 0:
            break
        got = _pull_pass(leave, remaining)
        pulled += got
        leftover = leftover_fn()
        if leftover <= 0:
            return {"pulled": pulled, "shortfall": leftover, "dipped": False}
        if got <= 0:
            break
        remaining = leftover + overhead

    if leftover > 0 and leave > PULL_HARD_LEAVE_CYCLES:
        want = leftover + overhead
        got = _pull_pass(PULL_HARD_LEAVE_CYCLES, want)
        if got > 0:
            pulled += got
            dipped = True
        leftover = leftover_fn()

    return {"pulled": pulled, "shortfall": leftover, "dipped": dipped}


def ensure_wallet_cycles(
    descriptor: Descriptor,
    *,
    network: str,
    identity: str,
    descriptor_path: Path | None,
) -> dict[str, Any]:
    """Pull sibling-treasury surplus until the deploy wallet plan is covered."""
    plan = build_cycles_plan(descriptor, network, identity=identity)
    shortfall = _wallet_shortfall(plan)

    def _leftover() -> int:
        nonlocal plan
        plan = build_cycles_plan(descriptor, network, identity=identity)
        return _wallet_shortfall(plan)

    result = _pull_sibling_surplus(
        descriptor,
        shortfall,
        network=network,
        identity=identity,
        descriptor_path=descriptor_path,
        leftover_fn=_leftover,
    )
    result["plan"] = plan
    return result


def ensure_wallet_has(
    descriptor: Descriptor,
    *,
    network: str,
    identity: str,
    descriptor_path: Path | None,
    required: int,
) -> dict[str, Any]:
    """Pull sibling surplus until the cycles ledger holds at least ``required``."""
    if required <= 0:
        return {"pulled": 0, "shortfall": 0, "dipped": False, "wallet": 0}

    def _wallet() -> int:
        try:
            balance = dfx.cycles_balance(network, identity=identity)
        except dfx.DfxError:
            return 0
        return int(balance or 0)

    def _leftover() -> int:
        return max(0, required - _wallet())

    shortfall = _leftover()
    result = _pull_sibling_surplus(
        descriptor,
        shortfall,
        network=network,
        identity=identity,
        descriptor_path=descriptor_path,
        leftover_fn=_leftover,
    )
    result["wallet"] = _wallet()
    return result


def ensure_canister_has(
    descriptor: Descriptor,
    canister_id: str,
    *,
    required: int,
    network: str,
    identity: str,
    descriptor_path: Path | None,
) -> dict[str, Any]:
    """Pull sibling surplus directly onto ``canister_id`` (no holding mint)."""
    dest = (canister_id or "").strip()
    if required <= 0 or not dest:
        return {"pulled": 0, "shortfall": 0, "dipped": False, "balance": 0}

    def _balance() -> int:
        try:
            status = dfx.canister_status(dest, network, identity=identity)
            value = dfx.parse_canister_cycles_balance(status.raw)
        except dfx.DfxError:
            return 0
        return int(value or 0)

    def _leftover() -> int:
        return max(0, required - _balance())

    shortfall = _leftover()
    result = _pull_sibling_surplus(
        descriptor,
        shortfall,
        network=network,
        identity=identity,
        descriptor_path=descriptor_path,
        leftover_fn=_leftover,
        destination=dest,
    )
    result["balance"] = _balance()
    return result


def refill_children_from_casals(
    casals_id: str,
    children: list[tuple[str, str, int]],
    *,
    surplus: int,
    network: str,
    identity: str,
) -> list[tuple[str, int]]:
    """Move dest-Casals surplus onto short orchestra children via ``top_up``.

    ``children`` is ``(name, canister_id, shortfall)``. Stops when surplus
    is exhausted. Returns ``[(name, amount_moved), ...]``.
    """
    if surplus <= 0 or not (casals_id or "").strip():
        return []
    moved: list[tuple[str, int]] = []
    remaining = surplus
    for name, _cid, shortfall in children:
        tree = ORCHESTRA_TREE_NAMES.get(name)
        send = min(int(shortfall), remaining)
        if not tree or send <= 0:
            continue
        result = _casals_call(
            casals_id,
            "top_up",
            {"canister": tree, "amount": send},
            network=network,
            identity=identity,
        )
        if result.get("ok") is False:
            raise RuntimeError(
                result.get("error") or f"Casals top_up {tree} failed"
            )
        remaining -= send
        moved.append((name, send))
    return moved


def format_cycles(amount: int | None) -> str:
    if amount is None:
        return "unknown"
    return _format_cycles(amount)
