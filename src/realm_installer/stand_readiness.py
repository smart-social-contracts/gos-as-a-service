"""Pure helpers for "is the conductor done building this stand?" (no IC imports).

The installer declares a stand with ``create_stand`` and the Casals conductor
materialises its canisters from the section's ``stand_template`` on its own
reconcile timer. These helpers read the ``get_tree`` JSON to decide when the
members the installer needs are usable.
"""

from __future__ import annotations

# ``Canister.status`` value Casals reports once code is installed and hash-verified.
CANISTER_INSTALLED = "installed"


def stand_required_members(stand: str) -> list[str]:
    """Template members the installer must see installed before bootstrapping."""
    return [f"{stand}-backend", f"{stand}-frontend"]


def installed_stand_canisters(tree: dict, stand: str) -> dict[str, str]:
    """``name -> canister_id`` for every canister of ``stand`` that has an id and
    is ``installed``. Canisters that are merely created (no code yet) are omitted."""
    out: dict[str, str] = {}
    for sec in (tree or {}).get("sections") or []:
        for st in sec.get("stands") or []:
            if (st.get("name") or "").strip() != stand:
                continue
            for c in st.get("canisters") or []:
                name = (c.get("name") or "").strip()
                cid = (c.get("canister_id") or "").strip()
                if name and cid and (c.get("status") or "").strip() == CANISTER_INSTALLED:
                    out[name] = cid
    return out


def stand_readiness(tree: dict, stand: str, required: list[str]) -> tuple[dict[str, str], list[str]]:
    """Return ``(installed, missing)``: the stand's installed canisters by name,
    and the ``required`` members that are not installed yet (empty when ready)."""
    installed = installed_stand_canisters(tree, stand)
    missing = [m for m in required if m not in installed]
    return installed, missing


def _stand_node(tree: dict, stand: str) -> dict | None:
    for sec in (tree or {}).get("sections") or []:
        for st in sec.get("stands") or []:
            if (st.get("name") or "").strip() == stand:
                return st
    return None


def stand_build_gate(tree: dict, stand: str) -> tuple[str, str]:
    """Whether a stand whose canisters are installed has finished its files.

    Casals sets ``status: installed`` when the wasm is on the canister, then
    keeps uploading the frontend. ``built`` becomes true only when that plan
    has nothing left, which includes the ``/index.html`` health check.
    ``build_error`` is why a build stopped.

    Returns ``("ready", "")``, ``("waiting", reason)``, or ``("failed", reason)``.
    """
    node = _stand_node(tree, stand)
    if node is None:
        return "waiting", f"{stand} is not in the conductor tree"
    error = (node.get("build_error") or "").strip()
    if error:
        return "failed", error
    if not node.get("built"):
        return "waiting", f"{stand} frontend assets are still uploading"
    return "ready", ""
