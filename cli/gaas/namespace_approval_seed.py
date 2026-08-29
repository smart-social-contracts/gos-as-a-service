"""Marketplace-attributed file-registry namespace approvals.

Realms refuse to install ``ext/`` and ``codex/`` packages unless the file
registry holds an approval attributed to the marketplace canister (not the
operator). ``verification_status`` on a marketplace listing is UI-only; the
install gate is ``get_namespace_approval_icc`` → ``approved: true``.

Approvals are bound to the current file hashes. A republish invalidates
``content_matches``, so first-party publish must stamp on *every* publish,
not as a one-shot seed.
"""

from __future__ import annotations

import json
from typing import Any

from gaas import dfx

INSTALLABLE_PREFIXES = ("ext/", "codex/")
DEFAULT_APPROVAL_NOTES = "First-party package, approved by gaas deploy seed"
PUBLISH_APPROVAL_NOTES = "First-party package, approved by gaas publish"
DEMO_ENVIRONMENT_NAMES = frozenset({"demo"})


class ApprovalStampError(RuntimeError):
    """Publish or seed could not leave a marketplace approval stamp."""


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
    """True when list_namespaces reports the install gate as closed.

    ``approved`` is already ``status == approved and content_matches``, so a
    republish that changes hashes shows up here as needing a restamp.
    """
    return not bool(entry.get("approved"))


def refuse_demo_environment(name: str) -> None:
    normalized = (name or "").strip().lower()
    if normalized in DEMO_ENVIRONMENT_NAMES:
        raise ApprovalStampError(
            "refusing to stamp namespace approvals on demo "
            "(test/staging pipelines only)"
        )


def candid_two_text(a: str, b: str) -> str:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    return f'("{esc(a)}", "{esc(b)}")'


def grant_marketplace_approver(
    registry_id: str,
    marketplace_id: str,
    network: str,
    identity: str | None,
) -> None:
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


def fetch_namespace_approval(
    registry_id: str,
    namespace: str,
    network: str,
    identity: str | None,
) -> dict[str, Any]:
    raw = dfx.canister_call(
        registry_id,
        "get_namespace_approval",
        dfx.candid_text_arg(json.dumps({"namespace": namespace})),
        network,
        identity=identity,
        query=True,
    )
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ApprovalStampError(
            f"get_namespace_approval({namespace}) returned unexpected payload: {raw!r}"
        )
    return payload


def approval_matches_current_hash(payload: dict[str, Any]) -> bool:
    return (
        payload.get("approved") is True and payload.get("content_matches") is True
    )


def assert_namespace_approved(
    payload: dict[str, Any],
    *,
    namespace: str,
) -> dict[str, Any]:
    if approval_matches_current_hash(payload):
        return payload
    raise ApprovalStampError(
        f"namespace {namespace} is not approved for the published hash "
        f"(approved={payload.get('approved')!r}, "
        f"content_matches={payload.get('content_matches')!r}, "
        f"status={payload.get('status')!r})"
    )


def stamp_namespace_approval(
    marketplace_id: str,
    namespace: str,
    network: str,
    identity: str | None,
    *,
    notes: str = PUBLISH_APPROVAL_NOTES,
) -> dict[str, Any]:
    """Call marketplace ``admin_approve_namespace`` so the stamp is marketplace-attributed."""
    response_raw = dfx.canister_call(
        marketplace_id,
        "admin_approve_namespace",
        candid_two_text(namespace, notes),
        network,
        identity=identity,
    )
    response = json.loads(response_raw)
    if not isinstance(response, dict):
        raise ApprovalStampError(
            f"admin_approve_namespace({namespace}) returned unexpected payload: "
            f"{response_raw!r}"
        )
    if response.get("success") is not True or response.get("error"):
        detail = response.get("error") or response
        raise ApprovalStampError(
            f"admin_approve_namespace({namespace}) refused: {detail}"
        )
    return response


def stamp_and_verify_namespace(
    registry_id: str,
    marketplace_id: str,
    namespace: str,
    network: str,
    identity: str | None,
    *,
    notes: str = PUBLISH_APPROVAL_NOTES,
    already_granted: bool = False,
) -> dict[str, Any]:
    """Stamp via marketplace, then require ``approved`` + ``content_matches``."""
    if not already_granted:
        grant_marketplace_approver(
            registry_id, marketplace_id, network, identity
        )
    stamp_namespace_approval(
        marketplace_id, namespace, network, identity, notes=notes
    )
    payload = fetch_namespace_approval(
        registry_id, namespace, network, identity
    )
    return assert_namespace_approved(payload, namespace=namespace)


def stamp_after_publish(
    registry_id: str,
    namespace: str,
    network: str,
    identity: str | None,
    *,
    marketplace_id: str | None,
) -> dict[str, Any] | None:
    """Finalize first-party publish: restamp ext/codex or refuse to publish.

    Non-installable namespaces (wasm, frontend, branding) are left alone.
    Local replica without a marketplace ID skips (same as seed). IC publish
    of ``ext/`` or ``codex/`` cannot succeed without the stamp.
    """
    if not is_installable_namespace(namespace):
        return None

    marketplace_id = (marketplace_id or "").strip()
    if not marketplace_id:
        if network in ("local", "localhost"):
            return None
        raise ApprovalStampError(
            f"cannot publish {namespace} without a marketplace approval stamp; "
            "pass marketplace_backend (admin_approve_namespace)"
        )

    return stamp_and_verify_namespace(
        registry_id,
        marketplace_id,
        namespace,
        network,
        identity,
        notes=PUBLISH_APPROVAL_NOTES,
    )


def seed_namespace_approvals(
    registry_id: str,
    marketplace_id: str,
    network: str,
    identity: str,
    *,
    force: bool = False,
    namespaces: list[str] | None = None,
    notes: str = DEFAULT_APPROVAL_NOTES,
) -> dict[str, int]:
    counts = {"granted": 0, "approved": 0, "skipped": 0, "failed": 0}
    registry_id = (registry_id or "").strip()
    marketplace_id = (marketplace_id or "").strip()
    if not registry_id or not marketplace_id:
        return counts

    grant_marketplace_approver(registry_id, marketplace_id, network, identity)
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

    wanted = {name.strip() for name in (namespaces or []) if name and name.strip()}
    attempted = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        namespace = str(entry.get("namespace") or "").strip()
        if not namespace or not is_installable_namespace(namespace):
            continue
        if wanted and namespace not in wanted:
            continue
        if not force and not needs_approval(entry):
            counts["skipped"] += 1
            continue

        attempted += 1
        try:
            stamp_and_verify_namespace(
                registry_id,
                marketplace_id,
                namespace,
                network,
                identity,
                notes=notes,
                already_granted=True,
            )
        except (json.JSONDecodeError, dfx.DfxError, ApprovalStampError, RuntimeError):
            counts["failed"] += 1
            continue
        counts["approved"] += 1

    if wanted:
        missing = wanted - {
            str(entry.get("namespace") or "").strip()
            for entry in entries
            if isinstance(entry, dict)
        }
        for namespace in sorted(missing):
            if not is_installable_namespace(namespace):
                continue
            attempted += 1
            try:
                stamp_and_verify_namespace(
                    registry_id,
                    marketplace_id,
                    namespace,
                    network,
                    identity,
                    notes=notes,
                    already_granted=True,
                )
            except (json.JSONDecodeError, dfx.DfxError, ApprovalStampError, RuntimeError):
                counts["failed"] += 1
                continue
            counts["approved"] += 1

    if attempted > 0 and counts["approved"] == 0:
        raise RuntimeError(
            f"all {attempted} namespace approval attempt(s) failed "
            f"({counts['failed']} failed)"
        )

    return counts
