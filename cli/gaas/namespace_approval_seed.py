"""Seed file-registry namespace approvals via the marketplace backend.

Realms refuse to install ``ext/`` and ``codex/`` packages without a marketplace-
attributed approval on the file registry. After catalog seeding uploads packages,
this module grants the marketplace approver ACL and records approvals bound to
current file hashes.
"""

from __future__ import annotations

import json
from typing import Any

from gaas import dfx

INSTALLABLE_PREFIXES = ("ext/", "codex/")
DEFAULT_APPROVAL_NOTES = "First-party package, approved by gaas deploy seed"


def is_installable_namespace(name: str) -> bool:
    return name.startswith(INSTALLABLE_PREFIXES)


def installable_namespaces_from_list(entries: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for entry in entries:
        namespace = str(entry.get("namespace") or "").strip()
        if namespace and is_installable_namespace(namespace):
            names.append(namespace)
    return names


def needs_approval(entry: dict[str, Any]) -> bool:
    return not bool(entry.get("approved"))


def candid_two_text(a: str, b: str) -> str:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    return f'("{esc(a)}", "{esc(b)}")'


def seed_namespace_approvals(
    registry_id: str,
    marketplace_id: str,
    network: str,
    identity: str,
) -> dict[str, int]:
    counts = {"granted": 0, "approved": 0, "skipped": 0, "failed": 0}
    registry_id = (registry_id or "").strip()
    marketplace_id = (marketplace_id or "").strip()
    if not registry_id or not marketplace_id:
        return counts

    grant_payload = json.dumps(
        {"namespace": "_approvers", "principal": marketplace_id}
    )
    dfx.canister_call(
        registry_id,
        "grant_publish",
        dfx.candid_text_arg(grant_payload),
        network,
        identity=identity,
    )
    counts["granted"] = 1

    raw = dfx.canister_call(
        registry_id,
        "list_namespaces",
        "()",
        network,
        identity=identity,
        query=True,
    )
    entries = json.loads(raw)
    if not isinstance(entries, list):
        raise RuntimeError(f"list_namespaces returned unexpected payload: {raw!r}")

    attempted = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        namespace = str(entry.get("namespace") or "").strip()
        if not namespace or not is_installable_namespace(namespace):
            continue
        if not needs_approval(entry):
            counts["skipped"] += 1
            continue

        attempted += 1
        try:
            response_raw = dfx.canister_call(
                marketplace_id,
                "admin_approve_namespace",
                candid_two_text(namespace, DEFAULT_APPROVAL_NOTES),
                network,
                identity=identity,
            )
            response = json.loads(response_raw)
        except (json.JSONDecodeError, dfx.DfxError, RuntimeError):
            counts["failed"] += 1
            continue

        if response.get("success") is True and not response.get("error"):
            counts["approved"] += 1
        else:
            counts["failed"] += 1

    if attempted > 0 and counts["approved"] == 0:
        raise RuntimeError(
            f"all {attempted} namespace approval attempt(s) failed "
            f"({counts['failed']} failed)"
        )

    return counts
