"""Casals drain-then-delete for stands, orphan canisters, and frontend-preserving rebuilds."""

from __future__ import annotations

import json
from typing import Any

from gaas import dfx
from gaas.descriptor import Descriptor
from gaas.known import KNOWN_CANISTER_NAMES, PLATFORM_CANISTER_NAMES

FRONTEND_NAME = "realm_registry_frontend"
MARKETPLACE_FRONTEND_NAME = "marketplace_frontend"
PRESERVED_FRONTEND_NAMES = (FRONTEND_NAME, MARKETPLACE_FRONTEND_NAME)
ORCHESTRA_BATCH = 1
EVAC_CHUNK = 10_000_000_000_000  # 10T
EVAC_MIN_RESERVE = 100_000_000_000  # 100B
CONDUCTOR_DELETE_MAX = 500_000_000_000  # 500B


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


def _casals_call(
    casals_id: str,
    method: str,
    payload: dict[str, Any],
    *,
    network: str,
    identity: str,
) -> dict[str, Any]:
    raw = dfx.canister_call(
        casals_id,
        method,
        dfx.candid_text_arg(json.dumps(payload)),
        network,
        identity=identity,
    )
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Casals {method} returned non-object JSON")
    return parsed


def _preserved_frontend_ids(descriptor: Descriptor) -> list[str]:
    frontend_id = (descriptor.canisters.get(FRONTEND_NAME) or "").strip()
    if not frontend_id:
        raise RuntimeError(f"descriptor.canisters.{FRONTEND_NAME} is required")

    preserved = [frontend_id]
    marketplace_id = (descriptor.canisters.get(MARKETPLACE_FRONTEND_NAME) or "").strip()
    if marketplace_id:
        preserved.append(marketplace_id)
    return preserved


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


def ensure_casals_controller(
    canister_id: str,
    *,
    casals_id: str,
    deployer_principal: str,
    network: str,
    identity: str,
) -> None:
    status = dfx.canister_status(canister_id, network, identity=identity)
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
) -> tuple[list[dict[str, Any]], int]:
    destroyed: list[dict[str, Any]] = []
    cycles_reclaimed = 0
    last_remaining: int | None = None
    stalled = 0

    while True:
        parsed = _casals_call(
            casals_id,
            "destroy_orchestra",
            {"preserve": preserve, "limit": batch},
            network=network,
            identity=identity,
        )
        if parsed.get("ok") is False:
            raise RuntimeError(parsed.get("error") or "destroy_orchestra failed")
        errors = parsed.get("errors") or []
        if errors:
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
            raise RuntimeError(
                parsed.get("error") or f"destroy_canister failed for {name} ({canister_id})"
            )
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
        if balance is None or balance <= evac_min_reserve:
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


def destroy_except_frontend(
    descriptor: Descriptor,
    *,
    network: str,
    identity: str,
) -> dict[str, Any]:
    casals_id = (descriptor.canisters.get("casals_backend") or "").strip()
    if not casals_id:
        raise RuntimeError("descriptor.canisters.casals_backend is required")

    preserved_frontend_ids = _preserved_frontend_ids(descriptor)
    preserve_set = set(preserved_frontend_ids)

    wallet = dfx.get_wallet(network, identity=identity)
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
        preserve=preserved_frontend_ids,
        network=network,
        identity=identity,
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
    if leftover > CONDUCTOR_DELETE_MAX:
        raise RuntimeError(
            f"Casals still holds {leftover} cycles "
            f"(refusing delete above {CONDUCTOR_DELETE_MAX})"
        )

    dfx.delete_dust_canister(
        casals_id,
        network,
        identity=identity,
        max_cycles=CONDUCTOR_DELETE_MAX,
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
        "cycles_reclaimed": cycles_reclaimed,
        "cycles_evacuated": cycles_evacuated,
        "destroyed": orchestra_destroyed + extra_destroyed,
        "conductor_destroyed": True,
    }
