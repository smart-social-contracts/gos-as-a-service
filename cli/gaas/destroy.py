"""Casals drain-then-delete for stands, orphan canisters, and frontend-preserving rebuilds."""

from __future__ import annotations

import json
import os
from typing import Any

from rich.console import Console

from gaas import dfx
from gaas.descriptor import Descriptor
from gaas.known import KNOWN_CANISTER_NAMES, PLATFORM_CANISTER_NAMES

console = Console()

FRONTEND_NAME = "realm_registry_frontend"
MARKETPLACE_FRONTEND_NAME = "marketplace_frontend"
PRESERVED_FRONTEND_NAMES = (FRONTEND_NAME, MARKETPLACE_FRONTEND_NAME)
ORCHESTRA_BATCH = 1
EVAC_CHUNK = 10_000_000_000_000  # 10T
EVAC_MIN_RESERVE = 500_000_000_000  # 500B — last chunk must stay above freeze + delete max
CONDUCTOR_DELETE_MAX = 500_000_000_000  # 500B
# After evacuate_treasury hits below_reserve, IC freeze still leaves ~500–800B
# on the conductor. That is dust, not a treasury — allow delete so rebuild
# can proceed. Never use this cap *before* evacuation.
CONDUCTOR_FREEZE_DUST_MAX = 2_000_000_000_000  # 2T
CASALS_DESTROY_TOPUP = 300_000_000_000  # 300B — enough to leave the 30-day freeze
HOLDING_ENV = "GAAS_CYCLES_HOLDING"


def destroy_via_casals(
    descriptor: Descriptor,
    *,
    network: str,
    identity: str,
    stand: str | None = None,
    canister_id: str | None = None,
    allow_platform: bool = False,
) -> dict[str, Any]:
    casals_id = (descriptor.canisters.get("casals_backend") or "").strip()
    if not casals_id:
        raise RuntimeError("descriptor.canisters.casals_backend is required for destroy")

    stand_name = (stand or "").strip()
    target_id = (canister_id or "").strip()
    if bool(stand_name) == bool(target_id):
        raise RuntimeError("exactly one of --stand or --canister-id is required")

    if stand_name:
        payload = json.dumps({"stand": stand_name})
        raw = dfx.canister_call(
            casals_id,
            "destroy_stand",
            dfx.candid_text_arg(payload),
            network,
            identity=identity,
        )
    else:
        platform_ids = {
            descriptor.canisters[name].strip()
            for name in PLATFORM_CANISTER_NAMES
            if (descriptor.canisters.get(name) or "").strip()
        }
        if target_id in platform_ids and not allow_platform:
            raise RuntimeError(
                f"{target_id} is a platform canister in the descriptor; "
                "wipe in place with `gaas new --reinstall-backends` instead of delete. "
                "Pass --platform only if destroy is intentional."
            )
        status = dfx.canister_status(target_id, network, identity=identity)
        if casals_id not in status.controllers:
            raise RuntimeError(
                f"Casals ({casals_id}) is not a controller of {target_id}; "
                "refusing raw delete. Add Casals as controller then retry."
            )
        payload = json.dumps({"canister_id": target_id})
        raw = dfx.canister_call(
            casals_id,
            "destroy_canister",
            dfx.candid_text_arg(payload),
            network,
            identity=identity,
        )

    parsed = json.loads(raw)
    if isinstance(parsed, dict) and parsed.get("ok") is False:
        raise RuntimeError(parsed.get("error") or "Casals destroy failed")
    return parsed


def _is_out_of_cycles_error(exc: BaseException) -> bool:
    text = str(exc)
    return "IC0207" in text or "out of cycles" in text.lower()


def _error_is_target_out_of_cycles(error: str, canister_id: str) -> bool:
    text = error or ""
    return canister_id in text and (
        "IC0207" in text
        or "out of cycles" in text.lower()
        or "install-code-not-enough-cycles" in text.lower()
    )


def _delete_if_too_poor_to_sweep(
    name: str,
    canister_id: str,
    *,
    network: str,
    identity: str,
) -> int:
    """Stop+delete when Casals cannot install the sweeper and the remainder is dust."""
    status = dfx.canister_status(canister_id, network, identity=identity)
    balance = dfx.parse_canister_cycles_balance(status.raw)
    if balance is None:
        raise RuntimeError(
            f"{name} ({canister_id}) sweeper install failed (out of cycles) "
            "and canister balance could not be read"
        )
    if balance > CONDUCTOR_DELETE_MAX:
        raise RuntimeError(
            f"{name} ({canister_id}) is too poor to install the Casals sweeper "
            f"but still holds {balance} cycles "
            f"(above {CONDUCTOR_DELETE_MAX} dust cap; top up or sweep manually)"
        )
    console.print(
        f"  {name} ({canister_id}) too poor to install sweep WASM; deleting directly "
        f"({balance} cycles burned)"
    )
    dfx.delete_dust_canister(
        canister_id,
        network,
        identity=identity,
        max_cycles=CONDUCTOR_DELETE_MAX,
    )
    return balance


def _casals_call(
    casals_id: str,
    method: str,
    payload: dict[str, Any],
    *,
    network: str,
    identity: str,
) -> dict[str, Any]:
    arg = dfx.candid_text_arg(json.dumps(payload))
    try:
        raw = dfx.canister_call(
            casals_id, method, arg, network, identity=identity
        )
    except dfx.DfxError as exc:
        if not _is_out_of_cycles_error(exc):
            raise
        dfx.top_up_canister(
            casals_id, CASALS_DESTROY_TOPUP, network, identity=identity
        )
        raw = dfx.canister_call(
            casals_id, method, arg, network, identity=identity
        )
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Casals {method} returned non-object JSON")
    return parsed


def _resolve_cycles_destination(
    network: str, identity: str
) -> tuple[str, bool]:
    """Return (holding_canister_id, ephemeral).

    Always use a dedicated holding canister for the evacuated treasury so the
    cycles are reserved for this run and cannot be double-spent by the shared
    cycles ledger. Reuse ``GAAS_CYCLES_HOLDING`` when set (resume after a
    failed destroy) instead of burning another 0.5T create fee. The holding is
    refunded to the ledger at the end of a successful run.
    """
    existing = (os.environ.get(HOLDING_ENV) or "").strip()
    if existing:
        return existing, True
    return dfx.create_ephemeral_canister(network, identity=identity), True


def _preserved_frontend_ids(descriptor: Descriptor) -> list[str]:
    frontend_id = (descriptor.canisters.get(FRONTEND_NAME) or "").strip()
    if not frontend_id:
        raise RuntimeError(f"descriptor.canisters.{FRONTEND_NAME} is required")

    preserved = [frontend_id]
    marketplace_id = (descriptor.canisters.get(MARKETPLACE_FRONTEND_NAME) or "").strip()
    if marketplace_id:
        preserved.append(marketplace_id)
    return preserved


def _orchestra_preserve_ids(descriptor: Descriptor) -> list[str]:
    """IDs passed to Casals ``destroy_orchestra``.

    Include every DNS-mapped frontend. On demo the marketplace frontend is a
    registered orchestra canister — omitting it lets ``destroy_orchestra``
    drain-delete it and burn ``demo.realmsgos.org``. Casals rejects unknown
    preserve entries (IDs not in its tree). The destroy loop drops those IDs
    and retries; if none remain, orchestra destroy is skipped because Casals
    cannot delete a canister it does not track (the DNS frontend stays).
    """
    return list(_preserved_frontend_ids(descriptor))


def _unknown_preserve_ids(message: str) -> list[str] | None:
    """Parse Casals ``unknown preserve entries: id, …``. ``None`` if unrelated."""
    text = str(message or "")
    if "unknown preserve" not in text.lower():
        return None
    _, _, rest = text.partition(":")
    return [part.strip().strip("'\"") for part in rest.split(",") if part.strip()]


def _also_destroy_targets(
    descriptor: Descriptor,
    *,
    preserve_ids: set[str],
    casals_id: str,
) -> list[tuple[str, str]]:
    skip_ids = set(preserve_ids) | {casals_id}
    seen: set[str] = set()
    targets: list[tuple[str, str]] = []
    for name in KNOWN_CANISTER_NAMES:
        cid = (descriptor.canisters.get(name) or "").strip()
        if not cid or cid in skip_ids or cid in seen:
            continue
        seen.add(cid)
        targets.append((name, cid))
    return targets


def _is_invalid_controller_error(message: str) -> bool:
    text = (message or "").lower()
    return "only the controllers" in text or "invalid-controller" in text


def ensure_casals_controller(
    canister_id: str,
    *,
    casals_id: str,
    deployer_principal: str,
    network: str,
    identity: str,
) -> None:
    try:
        status = dfx.canister_status(canister_id, network, identity=identity)
    except dfx.DfxError as exc:
        if dfx.is_canister_not_found_error(exc):
            return
        raise
    if casals_id in status.controllers:
        return
    if deployer_principal not in status.controllers:
        raise RuntimeError(
            f"cannot drain {canister_id}: Casals is not a controller and "
            f"identity {identity!r} is not a controller either"
        )
    controllers = list(status.controllers)
    if casals_id not in controllers:
        controllers.append(casals_id)
    dfx.update_canister_settings(canister_id, controllers, network, identity=identity)


def run_destroy_orchestra_loop(
    casals_id: str,
    *,
    preserve: list[str],
    network: str,
    identity: str,
    batch: int = ORCHESTRA_BATCH,
    deployer_principal: str = "",
) -> tuple[list[dict[str, Any]], int]:
    destroyed: list[dict[str, Any]] = []
    cycles_reclaimed = 0
    last_remaining: int | None = None
    stalled = 0
    preserve = list(preserve)
    ooc_deleted: set[str] = set()

    while True:
        try:
            parsed = _casals_call(
                casals_id,
                "destroy_orchestra",
                {"preserve": preserve, "limit": batch},
                network=network,
                identity=identity,
            )
        except dfx.DfxError as exc:
            parsed = {"ok": False, "error": str(exc)}
        if parsed.get("ok") is False:
            error = str(parsed.get("error") or "destroy_orchestra failed")
            unknown = _unknown_preserve_ids(error)
            if unknown is not None:
                drop = set(unknown)
                remaining = [cid for cid in preserve if cid not in drop]
                if remaining != preserve:
                    dropped = ", ".join(cid for cid in preserve if cid in drop)
                    preserve = remaining
                    if not preserve:
                        console.print(
                            "  [yellow]warning:[/yellow] Casals does not track "
                            f"preserve {dropped}; skipping destroy_orchestra "
                            "(DNS frontend is not in the orchestra and will not be deleted)",
                            highlight=False,
                            overflow="ignore",
                            crop=False,
                            no_wrap=True,
                        )
                        return destroyed, cycles_reclaimed
                    console.print(
                        "  [yellow]warning:[/yellow] Casals does not track "
                        f"preserve {dropped}; retrying destroy_orchestra "
                        f"with {', '.join(preserve)}",
                        highlight=False,
                        overflow="ignore",
                        crop=False,
                        no_wrap=True,
                    )
                    continue
            raise RuntimeError(error)
        errors = parsed.get("errors") or []
        if errors:
            fixed = 0
            ooc: list[tuple[str, str, str]] = []
            for err in errors:
                cid = str(err.get("canister_id") or "").strip()
                msg = str(err.get("error") or "")
                name = str(err.get("name") or cid)
                if cid and deployer_principal and _is_invalid_controller_error(msg):
                    ensure_casals_controller(
                        cid,
                        casals_id=casals_id,
                        deployer_principal=deployer_principal,
                        network=network,
                        identity=identity,
                    )
                    fixed += 1
                elif cid and _error_is_target_out_of_cycles(msg, cid):
                    ooc.append((name, cid, msg))
            if fixed:
                continue
            if ooc:
                progressed = False
                for name, cid, _msg in ooc:
                    if cid in ooc_deleted:
                        continue
                    burned = _delete_if_too_poor_to_sweep(
                        name,
                        cid,
                        network=network,
                        identity=identity,
                    )
                    ooc_deleted.add(cid)
                    destroyed.append(
                        {
                            "name": name,
                            "canister_id": cid,
                            "cycles_reclaimed": 0,
                            "cycles_burned": burned,
                        }
                    )
                    progressed = True
                if progressed:
                    continue
            raise RuntimeError(f"destroy_orchestra errors: {errors}")

        destroyed.extend(parsed.get("destroyed") or [])
        cycles_reclaimed += int(parsed.get("cycles_reclaimed") or 0)

        remaining = parsed.get("remaining")
        if last_remaining is not None and remaining == last_remaining:
            stalled += 1
            if stalled >= 2:
                raise RuntimeError(
                    f"destroy_orchestra made no progress (remaining stuck at {remaining})"
                )
        else:
            stalled = 0
        last_remaining = remaining

        if parsed.get("done"):
            break

    return destroyed, cycles_reclaimed


def also_destroy_descriptor_canisters(
    casals_id: str,
    targets: list[tuple[str, str]],
    *,
    network: str,
    identity: str,
) -> tuple[list[dict[str, Any]], int]:
    destroyed: list[dict[str, Any]] = []
    cycles_reclaimed = 0

    for name, canister_id in targets:
        try:
            dfx.canister_status(canister_id, network, identity=identity)
        except dfx.DfxError as exc:
            if dfx.is_canister_not_found_error(exc):
                continue
            raise

        parsed = _casals_call(
            casals_id,
            "destroy_canister",
            {"canister_id": canister_id},
            network=network,
            identity=identity,
        )
        if parsed.get("ok") is False:
            error = parsed.get("error") or (
                f"destroy_canister failed for {name} ({canister_id})"
            )
            if _error_is_target_out_of_cycles(error, canister_id):
                burned = _delete_if_too_poor_to_sweep(
                    name,
                    canister_id,
                    network=network,
                    identity=identity,
                )
                destroyed.append(
                    {
                        "name": name,
                        "canister_id": canister_id,
                        "cycles_reclaimed": 0,
                        "cycles_burned": burned,
                    }
                )
                continue
            raise RuntimeError(error)
        entry = {
            "name": name,
            "canister_id": canister_id,
            "cycles_reclaimed": int(parsed.get("cycles_reclaimed") or 0),
        }
        destroyed.append(entry)
        cycles_reclaimed += entry["cycles_reclaimed"]

    return destroyed, cycles_reclaimed


def convert_treasury_icp(
    casals_id: str,
    *,
    network: str,
    identity: str,
) -> dict[str, Any]:
    parsed = _casals_call(casals_id, "convert_treasury_icp", {}, network=network, identity=identity)
    if parsed.get("ok") is False or parsed.get("error"):
        raise RuntimeError(parsed.get("error") or "convert_treasury_icp failed")
    return parsed


def evacuate_treasury_to_wallet(
    casals_id: str,
    *,
    wallet: str,
    network: str,
    identity: str,
    evac_chunk: int = EVAC_CHUNK,
    evac_min_reserve: int = EVAC_MIN_RESERVE,
) -> int:
    cycles_evacuated = 0

    while True:
        status = dfx.canister_status(casals_id, network, identity=identity)
        balance = dfx.parse_canister_cycles_balance(status.raw)
        if (
            balance is None
            or balance <= evac_min_reserve
            or balance <= CONDUCTOR_DELETE_MAX
        ):
            break

        chunk = min(evac_chunk, balance - evac_min_reserve)
        reserve = balance - chunk
        parsed = _casals_call(
            casals_id,
            "evacuate_treasury",
            {"destination": wallet, "reserve": reserve},
            network=network,
            identity=identity,
        )
        if parsed.get("ok") is False:
            raise RuntimeError(parsed.get("error") or "evacuate_treasury failed")

        deposited = int(parsed.get("deposited") or 0)
        cycles_evacuated += deposited
        if deposited <= 0:
            break

    return cycles_evacuated


def clear_destroyed_descriptor_ids(
    descriptor: Descriptor,
    *,
    destroyed_ids: set[str],
    preserved_frontend_ids: set[str],
) -> None:
    for name in list(descriptor.canisters.keys()):
        cid = (descriptor.canisters.get(name) or "").strip()
        if name in PRESERVED_FRONTEND_NAMES and cid in preserved_frontend_ids:
            continue
        descriptor.canisters.pop(name, None)

    backend_id = (descriptor.multisig.backend_id or "").strip()
    if backend_id and backend_id in destroyed_ids:
        descriptor.multisig.backend_id = None


def _canister_is_live(
    canister_id: str,
    *,
    network: str,
    identity: str,
) -> bool:
    try:
        dfx.canister_status(canister_id, network, identity=identity)
    except dfx.DfxError as exc:
        if dfx.is_canister_not_found_error(exc):
            return False
        raise
    return True


def destroy_except_frontend(
    descriptor: Descriptor,
    *,
    network: str,
    identity: str,
) -> dict[str, Any]:
    preserved_frontend_ids = _preserved_frontend_ids(descriptor)
    preserve_set = set(preserved_frontend_ids)

    casals_id = (descriptor.canisters.get("casals_backend") or "").strip()
    casals_live = bool(casals_id) and _canister_is_live(
        casals_id, network=network, identity=identity
    )
    if not casals_live:
        orphans: list[tuple[str, str]] = []
        dead_ids: set[str] = set()
        for name, cid in list(descriptor.canisters.items()):
            cid = (cid or "").strip()
            if not cid:
                continue
            if name in PRESERVED_FRONTEND_NAMES and cid in preserve_set:
                continue
            if _canister_is_live(cid, network=network, identity=identity):
                orphans.append((name, cid))
            else:
                dead_ids.add(cid)
        if orphans:
            listing = ", ".join(f"{n} ({c})" for n, c in orphans)
            raise RuntimeError(
                "casals_backend is missing or already deleted, but these "
                "descriptor canisters are still live and cannot be drained: "
                + listing
            )
        clear_destroyed_descriptor_ids(
            descriptor,
            destroyed_ids=dead_ids,
            preserved_frontend_ids=preserve_set,
        )
        return {
            "ok": True,
            "preserved_frontend_ids": preserved_frontend_ids,
            "wallet": "",
            "ephemeral_holding": False,
            "cycles_reclaimed": 0,
            "cycles_evacuated": 0,
            "destroyed": [],
            "conductor_destroyed": True,
            "casals_already_gone": True,
        }

    existing_holding = (descriptor.holding_canister_id or "").strip()
    if existing_holding and _canister_is_live(
        existing_holding, network=network, identity=identity
    ):
        wallet, ephemeral_holding = existing_holding, True
        console.print(f"  cycles holding: resume {wallet}")
    else:
        wallet, ephemeral_holding = _resolve_cycles_destination(network, identity)
    deployer_principal = dfx.get_principal(identity)

    for name, canister_id in _also_destroy_targets(
        descriptor, preserve_ids=preserve_set, casals_id=casals_id
    ):
        ensure_casals_controller(
            canister_id,
            casals_id=casals_id,
            deployer_principal=deployer_principal,
            network=network,
            identity=identity,
        )

    orchestra_destroyed, orchestra_reclaimed = run_destroy_orchestra_loop(
        casals_id,
        preserve=_orchestra_preserve_ids(descriptor),
        network=network,
        identity=identity,
        deployer_principal=deployer_principal,
    )

    extra_targets = _also_destroy_targets(
        descriptor, preserve_ids=preserve_set, casals_id=casals_id
    )
    extra_destroyed, extra_reclaimed = also_destroy_descriptor_canisters(
        casals_id,
        extra_targets,
        network=network,
        identity=identity,
    )

    convert_treasury_icp(casals_id, network=network, identity=identity)

    cycles_evacuated = evacuate_treasury_to_wallet(
        casals_id,
        wallet=wallet,
        network=network,
        identity=identity,
    )

    status = dfx.canister_status(casals_id, network, identity=identity)
    leftover = dfx.parse_canister_cycles_balance(status.raw)
    if leftover is None:
        raise RuntimeError(f"could not read Casals balance for {casals_id}")
    delete_max = CONDUCTOR_DELETE_MAX
    if leftover > CONDUCTOR_DELETE_MAX:
        if leftover <= CONDUCTOR_FREEZE_DUST_MAX:
            delete_max = CONDUCTOR_FREEZE_DUST_MAX
        else:
            raise RuntimeError(
                f"Casals still holds {leftover} cycles "
                f"(refusing delete above {CONDUCTOR_FREEZE_DUST_MAX})"
            )

    dfx.delete_dust_canister(
        casals_id,
        network,
        identity=identity,
        max_cycles=delete_max,
    )

    if ephemeral_holding:
        descriptor.holding_canister_id = wallet
        console.print(
            f"  cycles holding: {wallet} (reserved for this run; "
            "refunded to ledger at the end)"
        )

    destroyed_ids = {
        entry["canister_id"]
        for entry in orchestra_destroyed + extra_destroyed
        if (entry.get("canister_id") or "").strip()
    }
    destroyed_ids.add(casals_id)
    clear_destroyed_descriptor_ids(
        descriptor,
        destroyed_ids=destroyed_ids,
        preserved_frontend_ids=preserve_set,
    )

    cycles_reclaimed = orchestra_reclaimed + extra_reclaimed
    return {
        "ok": True,
        "preserved_frontend_ids": preserved_frontend_ids,
        "wallet": wallet,
        "ephemeral_holding": ephemeral_holding,
        "cycles_reclaimed": cycles_reclaimed,
        "cycles_evacuated": cycles_evacuated,
        "destroyed": orchestra_destroyed + extra_destroyed,
        "conductor_destroyed": True,
    }
