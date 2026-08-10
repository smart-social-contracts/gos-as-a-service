"""Casals cycles preflight for on-chain realm provisioning."""

from __future__ import annotations

import json
from typing import Any

# Per-canister creation cost (conductor ``create_cycles`` setting).
PREFLIGHT_PER_CANISTER_CREATE_CYCLES = 2_000_000_000_000

# Buffer for orchestration / install operations after creation.
PREFLIGHT_OPS_MARGIN_CYCLES = 1_000_000_000_000

# Minimum balance required on file_registry (WASM pulls + bundle uploads).
DEFAULT_CYCLE_THRESHOLD_CYCLES = 2_000_000_000_000

FILE_REGISTRY_CANISTER_NAME = "file-registry"


def estimate_canister_creation_count(manifest: dict, *, create_stand_baton: bool) -> int:
    """Count canisters Casals will create for this deployment."""
    deploy_scope = (manifest.get("deploy_scope") or "both").strip()
    count = 0
    if deploy_scope in ("both", "backend_only"):
        count += 1
    if deploy_scope in ("both", "frontend_only"):
        count += 1
    if create_stand_baton:
        count += 1
    return count


def estimate_conductor_cycles_required(manifest: dict, *, create_stand_baton: bool) -> int:
    """Estimate conductor treasury spend for a new realm deployment."""
    return (
        estimate_canister_creation_count(manifest, create_stand_baton=create_stand_baton)
        * PREFLIGHT_PER_CANISTER_CREATE_CYCLES
        + PREFLIGHT_OPS_MARGIN_CYCLES
    )


def resolve_file_registry_id(manifest: dict, *, network: str, configured_id: str = "") -> str:
    infra = manifest.get("infra") or {}
    return (
        (infra.get("file_registry_canister_id") or "").strip()
        or (manifest.get("file_registry_canister_id") or "").strip()
        or (configured_id or "").strip()
    )


def parse_cycles_report(raw: str | dict | Any) -> dict:
    """Parse a Casals ``get_cycles_cached`` JSON payload."""
    if isinstance(raw, dict):
        return raw
    text = (raw if isinstance(raw, str) else str(raw or "")).strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def conductor_spendable(report: dict) -> int | None:
    treasury = report.get("treasury") or {}
    if not isinstance(treasury, dict):
        return None
    if treasury.get("spendable") is not None:
        return int(treasury["spendable"])
    if treasury.get("balance") is not None:
        return int(treasury["balance"])
    return None


def find_file_registry_row(report: dict) -> dict | None:
    for row in report.get("canisters") or []:
        if not isinstance(row, dict):
            continue
        if (row.get("name") or "").strip().lower() == FILE_REGISTRY_CANISTER_NAME:
            return row
    return None


def format_terse_cycles(n: int) -> str:
    if n >= 1_000_000_000_000:
        val = n / 1_000_000_000_000
        if val >= 10:
            return f"{val:.0f}T"
        text = f"{val:.2f}T"
        if text.endswith("0T"):
            return f"{val:.1f}T"
        return text
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}G"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    return str(n)


def format_top_up_command(canister_id: str, shortfall: int) -> str:
    amount = max(shortfall, 0)
    return f"dfx cycles top-up {canister_id} {amount} --network ic"


def _insufficient_cycles_error(
    label: str,
    canister_id: str,
    balance: int,
    required: int,
) -> str:
    shortfall = max(required - balance, 0)
    return (
        f"{label} {canister_id} has {format_terse_cycles(balance)}, "
        f"needs {format_terse_cycles(required)} "
        f"(shortfall {format_terse_cycles(shortfall)}); "
        f"top up: {format_top_up_command(canister_id, shortfall)}"
    )


def check_cycles_preflight(
    cycles_report: dict,
    *,
    casals_canister_id: str,
    required_conductor_cycles: int,
    file_registry_cycles: int | None = None,
    file_registry_id: str = "",
    file_registry_min_cycles: int | None = None,
) -> str | None:
    """Return an actionable error when treasury or file_registry is under-funded."""
    errors: list[str] = []
    min_cycles = file_registry_min_cycles or DEFAULT_CYCLE_THRESHOLD_CYCLES
    if min_cycles <= 0:
        min_cycles = DEFAULT_CYCLE_THRESHOLD_CYCLES

    spendable = conductor_spendable(cycles_report)
    if spendable is not None and spendable < required_conductor_cycles:
        errors.append(
            _insufficient_cycles_error(
                "conductor",
                casals_canister_id,
                spendable,
                required_conductor_cycles,
            )
        )

    fr_id = (file_registry_id or "").strip()
    fr_bal = file_registry_cycles
    if fr_bal is None:
        fr_row = find_file_registry_row(cycles_report)
        if fr_row is not None:
            if fr_row.get("cycles") is not None:
                fr_bal = int(fr_row["cycles"])
            if not fr_id:
                fr_id = (fr_row.get("canister_id") or "").strip()

    if fr_bal is not None and fr_id and fr_bal < min_cycles:
        errors.append(
            _insufficient_cycles_error(
                "file_registry",
                fr_id,
                fr_bal,
                min_cycles,
            )
        )

    if not errors:
        return None
    return "insufficient cycles: " + "; ".join(errors)


# Backward-compatible alias used by provisioning path during rollout.
check_casals_cycles_preflight = check_cycles_preflight
