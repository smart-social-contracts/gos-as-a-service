"""Persist descriptor canister IDs into repo inventory files.

``gaas new`` recreates non-DNS-mapped frontends (``casals_frontend``). The
temporary ``canister_ids.json`` mapping used by ``dfx deploy`` is restored
afterwards, which previously left the portal baking a dead ID. After create
or reinstall, the live ID must be written to ``canister_ids.json`` and
``dfx.json`` remote IDs under the *descriptor name* (staging/test/demo),
not under ``--network ic``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gaas.known import DFX_CANISTER_NAMES

_JSON_INDENT = 2

# ``dfx.json`` ``remote.id.<network>`` makes ``dfx build --network <network>``
# skip that canister. Never write a replica network here or local ``gaas new``
# produces no WASM.
_DFX_REMOTE_ENVS = frozenset({"test", "demo", "staging", "ic"})


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=_JSON_INDENT) + "\n", encoding="utf-8")


def align_ic_alias(repo_root: Path, descriptor: Any) -> dict[str, tuple[str, str]]:
    """Point every ``"ic"`` row in ``canister_ids.json`` at *descriptor*'s ids.

    test, staging and demo all deploy with ``--network ic``, and dfx keys the file
    by network — so they share one ``"ic"`` row per canister. ``dfx canister
    create <name> --network ic`` returns whatever id sits in that row, which made
    a staging deploy hand back test's live registry and installer and then
    reconfigure them as staging.

    The row is an alias for the environment being deployed right now: set from the
    descriptor, and removed where the descriptor has no id so a named create mints
    a canister instead of adopting another environment's.

    Returns the rows that changed, as ``{name: (old, new)}`` with ``""`` for absent.
    """
    ids_path = Path(repo_root) / "canister_ids.json"
    ids_data = _read_json(ids_path)
    canisters = getattr(descriptor, "canisters", None) or {}
    changed: dict[str, tuple[str, str]] = {}

    for name, entry in ids_data.items():
        if not isinstance(entry, dict):
            continue
        desired = (canisters.get(name) or "").strip()
        current = (entry.get("ic") or "").strip()
        if desired == current:
            continue
        if desired:
            entry["ic"] = desired
        else:
            entry.pop("ic", None)
        changed[name] = (current, desired)

    if changed:
        _write_json(ids_path, ids_data)
    return changed


def persist_descriptor_canister_ids(repo_root: Path, descriptor: Any) -> Path:
    """Write ``descriptor.canisters`` into ``canister_ids.json`` / ``dfx.json``.

    Keys use ``descriptor.name`` so a staging deploy with ``--network ic``
    updates the staging map the portal resolves on ``staging.gos.earth``.
    """
    root = Path(repo_root)
    env_key = (getattr(descriptor, "name", "") or "").strip()
    if not env_key:
        raise ValueError("descriptor.name is required to persist canister IDs")

    canisters = getattr(descriptor, "canisters", None) or {}
    ids_path = root / "canister_ids.json"
    ids_data = _read_json(ids_path)
    for name, canister_id in canisters.items():
        cid = (canister_id or "").strip()
        if not cid:
            continue
        entry = ids_data.setdefault(name, {})
        if not isinstance(entry, dict):
            entry = {}
            ids_data[name] = entry
        entry[env_key] = cid
    _write_json(ids_path, ids_data)

    if env_key in _DFX_REMOTE_ENVS:
        dfx_path = root / "dfx.json"
        dfx_data = _read_json(dfx_path)
        dfx_canisters = dfx_data.get("canisters")
        if isinstance(dfx_canisters, dict):
            changed = False
            for name, canister_id in canisters.items():
                cid = (canister_id or "").strip()
                if not cid:
                    continue
                dfx_name = DFX_CANISTER_NAMES.get(name) or name
                spec = dfx_canisters.get(dfx_name)
                if not isinstance(spec, dict):
                    continue
                remote = spec.get("remote")
                if not isinstance(remote, dict):
                    continue
                remote_ids = remote.get("id")
                if not isinstance(remote_ids, dict):
                    continue
                if remote_ids.get(env_key) != cid:
                    remote_ids[env_key] = cid
                    changed = True
            if changed:
                _write_json(dfx_path, dfx_data)

    return ids_path
