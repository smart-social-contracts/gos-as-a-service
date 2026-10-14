"""Pure helpers for "is the conductor done building this stand?" (no IC imports).

The installer declares a stand with ``stand_create`` and the Casals conductor
builds its canisters from the section's template on its own timer. These
helpers read the ``orchestra_get`` JSON (``canisters`` and ``stands``) to decide
when the members the installer needs are usable.
"""

from __future__ import annotations

# Canister statuses once code is installed and hash-verified (``ready`` = also handed off).
CANISTER_INSTALLED = ("installed", "ready")


def stand_required_members(stand: str) -> list[str]:
    """Template members the installer must see installed before bootstrapping."""
    return [f"{stand}-backend", f"{stand}-frontend"]


def installed_stand_canisters(view: dict, stand: str) -> dict[str, str]:
    """``name -> canister_id`` for every installed canister of ``stand``."""
    return {c["name"]: c["canister_id"] for c in (view or {}).get("canisters") or []
            if c.get("stand") == stand and c.get("canister_id") and c.get("status") in CANISTER_INSTALLED}


def stand_readiness(view: dict, stand: str, required: list[str]) -> tuple[dict[str, str], list[str]]:
    """Return ``(installed, missing)``: the stand's installed canisters by name,
    and the ``required`` members that are not installed yet (empty when ready)."""
    installed = installed_stand_canisters(view, stand)
    return installed, [m for m in required if m not in installed]


def _stand_node(view: dict, stand: str) -> dict | None:
    return next((s for s in (view or {}).get("stands") or [] if s.get("name") == stand), None)


def stand_declared(view: dict, stand: str) -> bool:
    return _stand_node(view, stand) is not None


def stand_build_gate(view: dict, stand: str) -> tuple[str, str]:
    """``("ready", "")``, ``("waiting", reason)`` or ``("failed", reason)``: the
    conductor sets ``built_at`` once every member is installed, its files are
    served and controllers are handed over; ``build_error`` is why a build stopped."""
    node = _stand_node(view, stand)
    if node is None:
        return "waiting", f"{stand} is not in the conductor tree"
    if (node.get("build_error") or "").strip():
        return "failed", node["build_error"].strip()
    if not node.get("built_at"):
        return "waiting", f"{stand} is still being built"
    return "ready", ""
