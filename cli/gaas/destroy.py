"""Casals drain-then-delete for stands, orphan canisters, and frontend-preserving rebuilds."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from gaas import dfx
from gaas.descriptor import Descriptor
from gaas.known import KNOWN_CANISTER_NAMES, PLATFORM_CANISTER_NAMES

FRONTEND_NAME = "realm_registry_frontend"
MARKETPLACE_FRONTEND_NAME = "marketplace_frontend"
PRESERVED_FRONTEND_NAMES = (FRONTEND_NAME, MARKETPLACE_FRONTEND_NAME)
ORCHESTRA_BATCH = 1
EVAC_CHUNK = 10_000_000_000_000  # 10T
EVAC_MIN_RESERVE = 500_000_000_000  # 500B — Casals keeps this so freeze + last delete succeed
# Must be strictly above EVAC_MIN_RESERVE: evacuate often leaves a few
# hundred B of slack (Basilisk freeze + a failed last micro-chunk).
CONDUCTOR_DELETE_MAX = 1_000_000_000_000  # 1T
CASALS_DESTROY_TOPUP = 300_000_000_000  # 300B — enough to leave the 30-day freeze
# Call + idle burn, not a real evacuate. deposit_cycles to IC0301 reports
# deposited=planned while treasury_after stays put; treat that as a stall.
EVAC_STALL_SLACK = 200_000_000_000  # 200B
HOLDING_ENV = "GAAS_CYCLES_HOLDING"
HOLDING_STATE_ENV = "GAAS_CYCLES_HOLDING_FILE"
HOLDING_STATE_NAME = "cycles_holding"
# Doomed non-DNS siblings we can evacuate onto when the ledger cannot mint a
# holding. Prefer asset/frontends we will refund-delete after the conductor
# is gone. Never the conductor itself or a DNS-mapped frontend.
HOLDING_FALLBACK_NAMES = (
    "casals_frontend",
    "file_registry_frontend",
    "casals_file_registry",
    "file_registry",
    "marketplace_backend",
    "realm_installer",
    "realm_registry_backend",
)


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


def _holding_state_path() -> Path:
    override = (os.environ.get(HOLDING_STATE_ENV) or "").strip()
    if override:
        return Path(override)
    return Path.home() / ".gaas" / HOLDING_STATE_NAME


def _read_persisted_holding() -> str:
    try:
        return _holding_state_path().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _persist_holding(canister_id: str) -> None:
    path = _holding_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canister_id.strip() + "\n", encoding="utf-8")


def _clear_persisted_holding() -> None:
    try:
        _holding_state_path().unlink()
    except OSError:
        pass


def _known_holding_ids() -> list[str]:
    ids: list[str] = []
    for cid in ((os.environ.get(HOLDING_ENV) or "").strip(), _read_persisted_holding()):
        if cid and cid not in ids:
            ids.append(cid)
    return ids


def _holding_is_live(canister_id: str, network: str, identity: str) -> bool:
    """False when the holding principal is already IC0301 / not found."""
    try:
        dfx.canister_status(canister_id, network, identity=identity)
    except dfx.DfxError as exc:
        if dfx.is_canister_not_found_error(exc):
            return False
        raise
    return True


def _holding_fallback_ids(
    descriptor: Descriptor,
    *,
    casals_id: str,
    preserve_ids: set[str],
) -> list[str]:
    """Live non-DNS siblings that can receive evacuated treasury cycles."""
    skip = set(preserve_ids) | {casals_id}
    found: list[str] = []
    for name in HOLDING_FALLBACK_NAMES:
        cid = (descriptor.canisters.get(name) or "").strip()
        if not cid or cid in skip or cid in found:
            continue
        found.append(cid)
    return found


def _resolve_cycles_destination(
    network: str,
    identity: str,
    *,
    fallback_ids: list[str] | None = None,
) -> tuple[str, bool]:
    """Return (canister_id, ephemeral_holding).

    Prefer a configured dfx wallet. When none exists, reuse a *live*
    ``GAAS_CYCLES_HOLDING`` or ``~/.gaas/cycles_holding`` (resume after a
    failed destroy) instead of burning another 0.5T create fee. A persisted
    ID that is already IC0301 is dropped so evacuate cannot spin forever.

    If the cycles ledger cannot mint a holding (empty after a successful
    prior ``gaas new``), reuse a doomed non-DNS sibling (typically
    ``casals_frontend``) and refund-delete it after the conductor is gone.
    """
    try:
        return dfx.get_wallet(network, identity=identity), False
    except dfx.DfxError:
        persisted = _read_persisted_holding()
        for existing in _known_holding_ids():
            if _holding_is_live(existing, network, identity):
                _persist_holding(existing)
                return existing, True
            if existing == persisted:
                _clear_persisted_holding()
        try:
            created = dfx.create_ephemeral_canister(network, identity=identity)
        except dfx.DfxError as exc:
            if not dfx.is_insufficient_cycles_error(exc):
                raise
            for cid in fallback_ids or []:
                if _holding_is_live(cid, network, identity):
                    _persist_holding(cid)
                    return cid, True
            raise RuntimeError(
                "cannot create a cycles holding: the identity cycles ledger "
                "is empty and no live non-DNS sibling is available to "
                "evacuate onto. Set GAAS_CYCLES_HOLDING or fund the ledger."
            ) from exc
        _persist_holding(created)
        return created, True


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
    preserve entries; the destroy loop retries without extras if that happens.
    """
    return list(_preserved_frontend_ids(descriptor))


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


def _unknown_preserve_ids(message: str) -> list[str]:
    """Parse Casals ``unknown preserve entries: id, id`` (not in the orchestra)."""
    marker = "unknown preserve entries:"
    lower = (message or "").lower()
    idx = lower.find(marker)
    if idx < 0:
        return []
    rest = message[idx + len(marker) :].strip()
    return [part.strip() for part in rest.split(",") if part.strip()]


def _drop_unknown_preserve(preserve: list[str], message: str) -> list[str] | None:
    """Drop IDs Casals does not know. None means the message is not that error."""
    unknown = set(_unknown_preserve_ids(message))
    if not unknown:
        return None
    dropped = [item for item in preserve if item not in unknown]
    if dropped == list(preserve):
        return None
    return dropped


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

    while True:
        if not preserve:
            # DNS frontends to keep are not in this orchestra (fresh conductor,
            # seed never finished). Casals also rejects an empty preserve list.
            # Extra descriptor canisters are drained by also_destroy instead.
            return destroyed, cycles_reclaimed
        try:
            parsed = _casals_call(
                casals_id,
                "destroy_orchestra",
                {"preserve": preserve, "limit": batch},
                network=network,
                identity=identity,
            )
        except dfx.DfxError as exc:
            dropped = _drop_unknown_preserve(preserve, str(exc))
            if dropped is not None:
                preserve = dropped
                continue
            raise
        if parsed.get("ok") is False:
            err = str(parsed.get("error") or "destroy_orchestra failed")
            dropped = _drop_unknown_preserve(preserve, err)
            if dropped is not None:
                preserve = dropped
                continue
            raise RuntimeError(err)
        errors = parsed.get("errors") or []
        if errors:
            fixed = 0
            for err in errors:
                cid = str(err.get("canister_id") or "").strip()
                msg = str(err.get("error") or "")
                if cid and deployer_principal and _is_invalid_controller_error(msg):
                    ensure_casals_controller(
                        cid,
                        casals_id=casals_id,
                        deployer_principal=deployer_principal,
                        network=network,
                        identity=identity,
                    )
                    fixed += 1
            if fixed:
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

        after_balance = parsed.get("treasury_after")
        if after_balance is None:
            after_status = dfx.canister_status(casals_id, network, identity=identity)
            after_balance = dfx.parse_canister_cycles_balance(after_status.raw)
        else:
            after_balance = int(after_balance)
        if after_balance is None:
            raise RuntimeError(
                f"evacuate_treasury deposited={deposited} but could not "
                f"read treasury balance for {casals_id}"
            )
        dropped = balance - after_balance
        if dropped <= EVAC_STALL_SLACK:
            raise RuntimeError(
                f"evacuate_treasury reported deposited={deposited} but "
                f"treasury only dropped {dropped} cycles "
                f"({balance} → {after_balance}); destination {wallet} "
                f"is likely gone (IC0301)"
            )

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


def _conductor_is_gone(casals_id: str, network: str, identity: str) -> bool:
    """True when the descriptor conductor is absent or already IC0301."""
    if not casals_id:
        return True
    try:
        dfx.canister_status(casals_id, network, identity=identity)
    except dfx.DfxError as exc:
        if dfx.is_canister_not_found_error(exc):
            return True
        raise
    return False


def _probe_conductor(
    casals_id: str, network: str, identity: str
) -> dfx.CanisterStatus | None:
    """Return conductor status, or None when the id is unset / IC0301."""
    if not casals_id:
        return None
    try:
        return dfx.canister_status(casals_id, network, identity=identity)
    except dfx.DfxError as exc:
        if dfx.is_canister_not_found_error(exc):
            return None
        raise


def _refund_uninstalled_rebuild(
    descriptor: Descriptor,
    *,
    network: str,
    identity: str,
    preserved_frontend_ids: list[str],
) -> dict[str, Any]:
    """Delete empty unfinished platform canisters so their cycles return to the ledger.

    Used when ``gaas new`` created canisters but never installed Casals. There is
    no orchestra to drain; the deployer is the sole controller.
    """
    preserve_set = set(preserved_frontend_ids)
    refunded: list[str] = []
    for name in list(descriptor.canisters):
        if name in PRESERVED_FRONTEND_NAMES:
            continue
        cid = (descriptor.canisters.get(name) or "").strip()
        if not cid:
            continue
        try:
            dfx.refund_canister_to_ledger(cid, network, identity=identity)
        except dfx.DfxError as exc:
            if dfx.is_canister_not_found_error(exc):
                continue
            raise
        refunded.append(cid)
    backend_id = (descriptor.multisig.backend_id or "").strip()
    if backend_id and backend_id not in preserve_set and backend_id not in refunded:
        try:
            dfx.refund_canister_to_ledger(backend_id, network, identity=identity)
            refunded.append(backend_id)
        except dfx.DfxError as exc:
            if not dfx.is_canister_not_found_error(exc):
                raise
    holding = _refund_leftover_holding(network, identity)
    clear_destroyed_descriptor_ids(
        descriptor,
        destroyed_ids=set(refunded),
        preserved_frontend_ids=preserve_set,
    )
    return {
        "ok": True,
        "preserved_frontend_ids": preserved_frontend_ids,
        "wallet": holding,
        "ephemeral_holding": False,
        "cycles_reclaimed": 0,
        "cycles_evacuated": 0,
        "destroyed": [{"canister_id": cid, "refunded": True} for cid in refunded],
        "conductor_destroyed": True,
        "conductor_uninstalled": True,
    }


def _refund_leftover_holding(network: str, identity: str) -> str:
    """Return leftover holding cycles to the ledger; never mint a new canister."""
    last = ""
    for holding in _known_holding_ids():
        last = holding
        try:
            dfx.refund_canister_to_ledger(holding, network, identity=identity)
        except dfx.DfxError as exc:
            if dfx.is_canister_not_found_error(exc):
                continue
            return holding
    _clear_persisted_holding()
    return last


def _already_gone_destroy_result(
    descriptor: Descriptor,
    *,
    network: str,
    identity: str,
    preserved_frontend_ids: list[str],
) -> dict[str, Any]:
    preserve_set = set(preserved_frontend_ids)
    destroyed_ids = {
        (descriptor.canisters.get(name) or "").strip()
        for name in list(descriptor.canisters)
        if name not in PRESERVED_FRONTEND_NAMES
    }
    destroyed_ids.discard("")
    backend_id = (descriptor.multisig.backend_id or "").strip()
    if backend_id:
        destroyed_ids.add(backend_id)
    clear_destroyed_descriptor_ids(
        descriptor,
        destroyed_ids=destroyed_ids,
        preserved_frontend_ids=preserve_set,
    )
    holding = _refund_leftover_holding(network, identity)
    return {
        "ok": True,
        "preserved_frontend_ids": preserved_frontend_ids,
        "wallet": holding,
        "ephemeral_holding": False,
        "cycles_reclaimed": 0,
        "cycles_evacuated": 0,
        "destroyed": [],
        "conductor_destroyed": False,
        "conductor_already_gone": True,
    }


def destroy_except_frontend(
    descriptor: Descriptor,
    *,
    network: str,
    identity: str,
) -> dict[str, Any]:
    preserved_frontend_ids = _preserved_frontend_ids(descriptor)
    preserve_set = set(preserved_frontend_ids)

    casals_id = (descriptor.canisters.get("casals_backend") or "").strip()
    conductor_status = _probe_conductor(casals_id, network, identity)
    if conductor_status is None:
        return _already_gone_destroy_result(
            descriptor,
            network=network,
            identity=identity,
            preserved_frontend_ids=preserved_frontend_ids,
        )
    if conductor_status.module_hash_missing is True:
        return _refund_uninstalled_rebuild(
            descriptor,
            network=network,
            identity=identity,
            preserved_frontend_ids=preserved_frontend_ids,
        )

    fallback_ids = _holding_fallback_ids(
        descriptor, casals_id=casals_id, preserve_ids=preserve_set
    )
    wallet, ephemeral_holding = _resolve_cycles_destination(
        network, identity, fallback_ids=fallback_ids
    )
    orchestra_preserve = _orchestra_preserve_ids(descriptor)
    if ephemeral_holding and wallet and wallet not in orchestra_preserve:
        # Sibling holding is still in the orchestra — keep it through
        # destroy_orchestra so evacuate has a live destination.
        orchestra_preserve.append(wallet)
        preserve_set.add(wallet)
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
        preserve=orchestra_preserve,
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

    if ephemeral_holding:
        dfx.refund_canister_to_ledger(wallet, network, identity=identity)

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
