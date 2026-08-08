"""Pure helpers for deferring Casals stand baton hand-off until post-bootstrap.

The installer must remain an IC controller on realm canisters through
``set_quarter_provisioning_config``, extension installs, and the
``schedule_registration`` backend/frontend prep calls. Baton hand-off
(via ``orchestration_hand_to_baton``) removes the installer from the
controller set, so it runs only after those steps complete.
"""

from __future__ import annotations

import json
from typing import Any

# Documented pipeline ordering for tests (indices must stay monotonic).
PROVISION_PIPELINE_STEPS = (
    "stand_create",
    "backend_canister",
    "frontend_canister",
    "token_canister",
    "defer_baton_record",
    "set_commander",
    "quarter_provisioning_config",
    "extensions_or_registration_schedule",
)

REGISTRATION_PIPELINE_STEPS = (
    "frontend_canister_ids",
    "backend_realm_config",
    "backend_canister_config",
    "branding_and_pins",
    "baton_handoff_execute",
    "registry_register",
)


def build_baton_handoff_payload(
    *,
    stand: str,
    casals_id: str,
    baton_key: str,
    hand_targets: list[tuple[str, str]],
    backend_id: str,
) -> dict[str, Any]:
    """Serialize everything ``_setup_stand_baton`` needs for a later run."""
    return {
        "stand": stand,
        "casals_id": casals_id,
        "baton_key": baton_key,
        "hand_targets": [[name, cid] for name, cid in hand_targets if cid],
        "backend_id": backend_id or "",
    }


def encode_baton_handoff_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"))


def decode_baton_handoff_payload(raw: str) -> dict[str, Any]:
    data = json.loads(raw or "{}")
    if not isinstance(data, dict):
        raise ValueError("baton_handoff_json must be a JSON object")
    return data


def hand_targets_from_payload(payload: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for item in payload.get("hand_targets") or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            name, cid = str(item[0]), str(item[1])
            if cid:
                out.append((name, cid))
    return out


def should_record_deferred_baton(
    *,
    create_stand_baton: bool,
    baton_pending: int,
    baton_canister_id: str,
) -> bool:
    """True when provision_via_casals should queue baton for a later hand-off."""
    if not create_stand_baton:
        return False
    if (baton_canister_id or "").strip():
        return False
    return True


def should_run_deferred_baton_handoff(
    *,
    baton_pending: int,
    baton_canister_id: str,
    create_stand_baton: bool,
) -> bool:
    """True when schedule_registration should execute the pending hand-off."""
    if not create_stand_baton:
        return False
    if not int(baton_pending or 0):
        return False
    if (baton_canister_id or "").strip():
        return False
    return True


def assert_baton_after_bootstrap(provision_steps: tuple[str, ...], registration_steps: tuple[str, ...]) -> None:
    """Guard that baton record/hand-off sit after bootstrap and before registry."""
    defer_idx = provision_steps.index("defer_baton_record")
    ext_idx = provision_steps.index("extensions_or_registration_schedule")
    assert defer_idx < ext_idx, "baton deferral must be recorded before extensions/registration"

    exec_idx = registration_steps.index("baton_handoff_execute")
    reg_idx = registration_steps.index("registry_register")
    assert exec_idx < reg_idx, "baton hand-off must complete before registry.register_realm"
