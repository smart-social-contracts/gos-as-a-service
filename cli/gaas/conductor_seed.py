"""Seed Casals conductor orchestra: templates, authorized WASMs, sheet, multisig."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from rich.console import Console

from gaas import dfx
from gaas.runlog import get_run_log, run_subprocess
from gaas.descriptor import Descriptor
from gaas.known import GOS_IMPLEMENTATIONS
from gaas.file_registry_client import fetch_namespace_hashes, upload_file
from gaas.platform import (
    find_gos_repo_root,
    find_local_assetstorage_wasm,
    require_casals_checkout,
)
from gaas.versions import resolve_deploy_version

console = Console()

CASALS_TEMPLATES_NAMESPACE = "casals-templates"

# Latest orchestration template versions from Casals seed/templates.json.
ORCHESTRATION_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    ("orchestration-baton", "1.3.0", "orchestration-baton@1.3.0.wasm.gz"),
    ("orchestration-multisig", "1.2.0", "orchestration-multisig@1.2.0.wasm.gz"),
)


def platform_sheet_path(repo_root: Path | None = None) -> Path:
    """Repo-root ``casals.json`` used by ``gaas new``."""
    root = repo_root or find_gos_repo_root()
    return root / "casals.json"


def platform_sheet(repo_root: Path | None = None) -> dict[str, Any]:
    """Load the GaaS Casals sheet (Infra stands + empty Deployments)."""
    path = platform_sheet_path(repo_root)
    if not path.is_file():
        raise FileNotFoundError(f"GaaS Casals sheet not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_casals_json(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError(f"expected JSON object from Casals, got {type(data).__name__}")
    if not data.get("ok", True):
        raise RuntimeError(data.get("error") or data.get("message") or str(data))
    return data


def _casals_call(
    casals_id: str,
    method: str,
    payload: dict[str, Any] | str,
    network: str,
    *,
    identity: str | None = None,
    query: bool = False,
) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    raw = dfx.canister_call(
        casals_id,
        method,
        dfx.candid_text_arg(text),
        network,
        identity=identity,
        query=query,
    )
    return _parse_casals_json(raw)


def get_tree(
    casals_id: str,
    network: str,
    *,
    identity: str | None = None,
) -> dict[str, Any]:
    raw = dfx.canister_call(
        casals_id,
        "get_tree",
        "()",
        network,
        identity=identity,
        query=True,
    )
    return json.loads(raw)


def _section_names(tree: dict[str, Any]) -> set[str]:
    return {sec.get("name", "") for sec in tree.get("sections") or []}


def _find_canister_id(tree: dict[str, Any], name: str) -> str:
    for sec in tree.get("sections") or []:
        for stand in sec.get("stands") or []:
            for canister in stand.get("canisters") or []:
                if (canister.get("name") or "").strip() == name:
                    return (canister.get("canister_id") or "").strip()
    return ""


def _canister_names(tree: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for sec in tree.get("sections") or []:
        for stand in sec.get("stands") or []:
            for canister in stand.get("canisters") or []:
                name = (canister.get("name") or "").strip()
                if name:
                    names.add(name)
    return names


def backends_before_frontends(
    platform_canisters: list[tuple[str, str, str]],
) -> list[tuple[str, str, str]]:
    """Order platform stand registration: backends first, then frontends.

    Casals ``register_canister`` for a backend grants Commit on any frontend
    already on the same stand. A newly minted Casals is not yet a controller of
    an adopted DNS frontend, so that grant fails with ManagePermissions. Putting
    backends first avoids the grant on a first-create. Resume still has to drop
    an already-registered frontend record before remaining backends (orchestra
    only — the IC canister is kept).
    """
    backends = [
        item for item in platform_canisters if (item[2] or "").lower() != "frontend"
    ]
    frontends = [
        item for item in platform_canisters if (item[2] or "").lower() == "frontend"
    ]
    return backends + frontends


def list_authorized_keys(
    casals_id: str,
    network: str,
    *,
    identity: str | None = None,
) -> dict[str, str]:
    raw = dfx.canister_call(
        casals_id,
        "list_authorized_wasms",
        dfx.candid_text_arg("{}"),
        network,
        identity=identity,
        query=True,
    )
    entries = json.loads(raw)
    if not isinstance(entries, list):
        return {}
    return {item.get("key", ""): item.get("wasm_hash", "") for item in entries}


def _resolve_template_wasm(casals_root: Path, filename: str) -> Path:
    path = casals_root / "seed" / "templates" / filename
    if path.is_file():
        return path
    script = casals_root / "scripts" / "build_orchestration_templates.sh"
    if script.is_file():
        run_log = get_run_log()
        if run_log is not None:
            run_log.run_step(
                "building orchestration templates (Motoko/basilisk)",
                ["bash", str(script)],
                cwd=casals_root,
            )
        else:
            console.print("  building orchestration templates (Motoko/basilisk)...")
            run_subprocess(["bash", str(script)], cwd=casals_root, check=True)
    if not path.is_file():
        raise RuntimeError(
            f"missing orchestration template {path}; "
            "run `make build-templates` in the Casals checkout"
        )
    return path


def _gunzip_bytes(path: Path) -> bytes:
    with gzip.open(path, "rb") as handle:
        return handle.read()


def orchestration_template_actions(
    authorized_hash: str | None,
    registry_hash: str | None,
    digest: str,
) -> tuple[bool, bool]:
    """Return (needs_upload, needs_authorize)."""
    needs_upload = (registry_hash or "") != digest
    needs_authorize = (authorized_hash or "") != digest
    return needs_upload, needs_authorize


def _upload_wasm_to_registry(
    registry_id: str,
    namespace: str,
    registry_path: str,
    wasm_bytes: bytes,
    network: str,
    *,
    identity: str | None = None,
) -> str:
    digest = hashlib.sha256(wasm_bytes).hexdigest()
    work = Path("/tmp") / "gaas-conductor-seed"
    work.mkdir(parents=True, exist_ok=True)
    local = work / registry_path.replace("/", "_")
    local.write_bytes(wasm_bytes)
    # upload_file returns a status string; the registry verifies expected_sha256
    # server-side during finalize, so a non-failed result means the digest holds.
    result = upload_file(
        registry_id,
        namespace,
        registry_path,
        local,
        network,
        identity=identity,
    )
    if result == "failed":
        raise RuntimeError(f"upload failed for {namespace}/{registry_path}")
    return digest


def seed_orchestration_templates(
    casals_id: str,
    registry_id: str,
    network: str,
    *,
    identity: str | None = None,
    casals_src: Path | None = None,
) -> None:
    casals_root = require_casals_checkout(casals_src)

    existing = list_authorized_keys(casals_id, network, identity=identity)
    registry_hashes = fetch_namespace_hashes(
        registry_id, CASALS_TEMPLATES_NAMESPACE, network, identity=identity
    )
    for family, version, filename in ORCHESTRATION_TEMPLATES:
        key = f"{family}@{version}"
        registry_path = key.replace("@", "@") + ".wasm" if "@" in filename else f"{family}.wasm"
        if family == "orchestration-baton":
            registry_path = "orchestration-baton@1.3.0.wasm"
        elif family == "orchestration-multisig":
            registry_path = "orchestration-multisig@1.2.0.wasm"

        gz_path = _resolve_template_wasm(casals_root, filename)
        wasm_bytes = _gunzip_bytes(gz_path)
        digest = hashlib.sha256(wasm_bytes).hexdigest()
        needs_upload, needs_authorize = orchestration_template_actions(
            existing.get(key), registry_hashes.get(registry_path), digest
        )
        if not needs_upload and not needs_authorize:
            console.print(f"  {key}: already authorized and on registry")
            continue

        if needs_upload:
            if not needs_authorize:
                console.print(
                    f"  {key}: re-uploading (registry hash missing or wrong)..."
                )
            else:
                console.print(f"  uploading + authorizing {key}...")
            _upload_wasm_to_registry(
                registry_id,
                CASALS_TEMPLATES_NAMESPACE,
                registry_path,
                wasm_bytes,
                network,
                identity=identity,
            )
            registry_hashes[registry_path] = digest
        elif needs_authorize:
            console.print(f"  authorizing {key}...")

        if needs_authorize:
            _casals_call(
                casals_id,
                "add_authorized_wasm",
                {
                    "key": family,
                    "version": version,
                    "registry_namespace": CASALS_TEMPLATES_NAMESPACE,
                    "registry_path": registry_path,
                    "wasm_hash": digest,
                    "kind": "backend",
                    "wasm_type": "baton" if family == "orchestration-baton" else "multisig",
                    "description": f"GaaS-seeded {key}",
                },
                network,
                identity=identity,
            )


def ensure_assetstorage_wasm(
    registry_id: str,
    version: str,
    network: str,
    *,
    identity: str | None = None,
    repo_root: Path | None = None,
) -> tuple[str, str, str]:
    """Upload realm certified-assets wasm to file_registry; return (namespace, path, sha256)."""
    namespace = f"wasm/realm-assetstorage/{version}"
    registry_path = "realms-assetstorage.wasm.gz"
    local_path = find_local_assetstorage_wasm(repo_root)
    digest = hashlib.sha256(local_path.read_bytes()).hexdigest()
    existing = fetch_namespace_hashes(
        registry_id, namespace, network, identity=identity
    )
    if existing.get(registry_path) == digest:
        return namespace, registry_path, digest
    result = upload_file(
        registry_id,
        namespace,
        registry_path,
        local_path,
        network,
        identity=identity,
        existing_hashes=existing,
    )
    if result == "failed":
        raise RuntimeError(f"upload failed for {namespace}/{registry_path}")
    return namespace, registry_path, digest


def authorize_gos_entry(
    casals_id: str,
    registry_id: str,
    descriptor: Descriptor,
    entry,
    network: str,
    *,
    identity: str | None = None,
    session=None,
    repo_root: Path | None = None,
) -> dict[str, str]:
    resolved = resolve_deploy_version(entry.version, entry.release_repo, session=session)
    version = resolved.catalog_version
    backend_ns = f"wasm/{entry.artifacts.backend_wasm_key}/{version}"
    frontend_ns = f"frontend/{entry.artifacts.frontend_wasm_key}/{version}"
    backend_path = entry.artifacts.resolved_backend_asset(entry.implementation)

    backend_hashes = fetch_namespace_hashes(
        registry_id, backend_ns, network, identity=identity
    )
    if not backend_hashes or backend_path not in backend_hashes:
        raise RuntimeError(
            f"file_registry missing {backend_ns}/{backend_path}; "
            "run seed_file_registry first"
        )
    backend_hash = backend_hashes[backend_path]

    existing = list_authorized_keys(casals_id, network, identity=identity)
    impl = GOS_IMPLEMENTATIONS.get(entry.implementation)
    wasm_type = impl.wasm_type if impl else "basilisk"

    backend_key = f"{entry.artifacts.backend_wasm_key}@{version}"
    if existing.get(backend_key) == backend_hash:
        backend_status = "already_authorized"
        console.print(f"  {backend_key}: already authorized")
    else:
        backend_status = "authorized"
        console.print(f"  authorizing {backend_key} from {backend_ns}...")
        _casals_call(
            casals_id,
            "add_authorized_wasm",
            {
                "key": entry.artifacts.backend_wasm_key,
                "version": version,
                "registry_namespace": backend_ns,
                "registry_path": backend_path,
                "wasm_hash": backend_hash,
                "kind": "backend",
                "wasm_type": wasm_type,
                "description": f"GaaS {entry.implementation} backend {version}",
            },
            network,
            identity=identity,
        )

    frontend_key = f"{entry.artifacts.frontend_wasm_key}@{version}"
    fe_ns, fe_path, fe_hash = ensure_assetstorage_wasm(
        registry_id,
        version,
        network,
        identity=identity,
        repo_root=repo_root,
    )
    # Always upsert: the hash-only check cannot detect drift in fields like
    # bundle_namespace on an existing entry, and the conductor's upsert is
    # idempotent. bundle_namespace points at the seeded dist bundle so the
    # conductor uploads it right after installing the assetstorage wasm.
    console.print(f"  authorizing {frontend_key} from {fe_ns}...")
    _casals_call(
        casals_id,
        "add_authorized_wasm",
        {
            "key": entry.artifacts.frontend_wasm_key,
            "version": version,
            "registry_namespace": fe_ns,
            "registry_path": fe_path,
            "wasm_hash": fe_hash,
            "kind": "frontend",
            "wasm_type": "assets",
            "bundle_namespace": frontend_ns,
            "description": (
                f"GaaS {entry.implementation} frontend {version} "
                "(certified-assets wasm)"
            ),
        },
        network,
        identity=identity,
    )
    return {
        "backend_key": backend_key,
        "backend_hash": backend_hash,
        "backend_status": backend_status,
        "frontend_key": frontend_key,
        "frontend_hash": fe_hash,
        "frontend_status": "authorized",
    }


def ensure_sheet_and_deploy_multisig(
    casals_id: str,
    network: str,
    *,
    identity: str | None = None,
) -> None:
    tree = get_tree(casals_id, network, identity=identity)
    sections = _section_names(tree)
    need_sheet = "Infra" not in sections or "Deployments" not in sections
    multisig_id = _find_canister_id(tree, "multisig")

    if need_sheet:
        sheet = platform_sheet()
        console.print("  set_sheet (Infra + Deployments)...")
        _casals_call(casals_id, "set_sheet", sheet, network, identity=identity)

    if not multisig_id:
        console.print("  deploy_sheet (governance/multisig)...")
        result = _casals_call(
            casals_id,
            "deploy_sheet",
            {"sheet": platform_sheet()},
            network,
            identity=identity,
        )
        created = result.get("created_canisters") or []
        if created:
            console.print(f"  created canisters: {', '.join(created)}")
        errors = result.get("errors") or []
        if errors:
            raise RuntimeError(f"deploy_sheet errors: {errors}")
        tree = get_tree(casals_id, network, identity=identity)
        multisig_id = _find_canister_id(tree, "multisig")
        if not multisig_id:
            raise RuntimeError("deploy_sheet completed but multisig not found in get_tree")
    else:
        console.print(f"  multisig: adopt {multisig_id}")


# Orchestra stand names must match gos-as-a-service/casals.json.
# Fleet file-registry is Product-owned (realms/casals.json) — do not map it here.
# A lumped "platform" stand with backend+frontend together tripped ManagePermissions.
PLATFORM_CANISTER_STAND: dict[str, str] = {
    "realm-installer": "installer",
    "realm-registry-backend": "realm-registry",
    "realm-registry-frontend": "realm-registry",
    "casals-file-registry": "casals-file-registry",
}

PLATFORM_STAND_DESCRIPTIONS: dict[str, str] = {
    "installer": "Installer backend.",
    "realm-registry": "Realm registry backend and DNS frontend (keep-ID reinstall).",
    "casals-file-registry": "Casals-owned file registry from casals new.",
}


def platform_stand_for(canister_name: str) -> str:
    """Return the Infra stand that should own ``canister_name``."""
    stand = PLATFORM_CANISTER_STAND.get(canister_name)
    if not stand:
        raise RuntimeError(
            f"no Casals stand mapping for platform canister {canister_name!r}"
        )
    return stand


def ensure_platform_stand(
    casals_id: str,
    platform_canisters: list[tuple[str, str, str]],
    network: str,
    *,
    identity: str | None = None,
) -> None:
    """Ensure Infra stands exist and register platform canisters onto them."""
    needed_stands: list[str] = []
    for name, _cid, _kind in platform_canisters:
        stand = platform_stand_for(name)
        if stand not in needed_stands:
            needed_stands.append(stand)
    for stand_name in needed_stands:
        try:
            _casals_call(
                casals_id,
                "create_stand",
                {
                    "section": "Infra",
                    "name": stand_name,
                    "description": PLATFORM_STAND_DESCRIPTIONS.get(
                        stand_name, stand_name
                    ),
                },
                network,
                identity=identity,
            )
            console.print(f"  create_stand (Infra/{stand_name})...")
        except RuntimeError as exc:
            if "already exists" not in str(exc).lower():
                raise
            console.print(f"  {stand_name} stand: already exists")

    tree = get_tree(casals_id, network, identity=identity)
    existing = _canister_names(tree)
    ordered = backends_before_frontends(platform_canisters)
    pending_backends = [
        name
        for name, _cid, kind in ordered
        if (kind or "").lower() != "frontend" and name not in existing
    ]
    if pending_backends:
        for name, _cid, kind in ordered:
            if (kind or "").lower() != "frontend" or name not in existing:
                continue
            console.print(
                f"  {name}: unregister orchestra record "
                "(register remaining backends before frontends)"
            )
            _casals_call(
                casals_id,
                "delete_canister",
                {"canister": name},
                network,
                identity=identity,
            )
            existing.discard(name)
    for name, canister_id, kind in ordered:
        if name in existing:
            console.print(f"  {name}: skip (already registered)")
        else:
            console.print(f"  {name}: register {canister_id} ({kind})")
            _casals_call(
                casals_id,
                "register_canister",
                {
                    "stand": platform_stand_for(name),
                    "name": name,
                    "canister_id": canister_id,
                    "kind": kind,
                },
                network,
                identity=identity,
            )


DEPLOYMENTS_COMMANDER_PERMISSIONS = [
    "stand.create",
    "stand.rename",
    "stand.delete",
    "canister.create",
    "canister.deploy",
    "canister.delete",
    "canister.lifecycle",
    "canister.topup",
    "commander.assign",
    "orchestration.baton.create",
    "orchestration.baton.upgrade",
    "orchestration.baton.hand_off",
    "orchestration.managed_upgrade.run",
]


def ensure_deployments_commander(
    casals_id: str,
    installer_id: str,
    network: str,
    *,
    identity: str | None = None,
) -> None:
    """Grant the installer section-commander rights on Deployments.

    Sheet ``commanders`` need a concrete principal; the installer ID is only
    known after mint, and ``$self`` is not expanded there. This set_commander
    call runs after sheet deploy. Section commander permissions cascade to
    stands, and set_commander adds-or-updates without removing others, so this
    is safely idempotent.
    """
    _casals_call(
        casals_id,
        "set_commander",
        {
            "section": "Deployments",
            "commander_principal": installer_id,
            "permissions": DEPLOYMENTS_COMMANDER_PERMISSIONS,
        },
        network,
        identity=identity,
    )
    console.print(f"  Deployments commander: {installer_id}")


def ensure_section_commanders(
    casals_id: str,
    sections: list[str] | set[str],
    principals: list[str],
    network: str,
    *,
    identity: str | None = None,
) -> None:
    """Grant all-permissions section commander rights on every orchestra section.

    Omitting ``permissions`` in set_commander grants full commander rights, which
    unlocks the Casals web UI for those principals. set_commander adds-or-updates,
    so repeated calls are safely idempotent.
    """
    if not principals:
        return
    for section in sections:
        for principal in principals:
            _casals_call(
                casals_id,
                "set_commander",
                {
                    "section": section,
                    "commander_principal": principal,
                },
                network,
                identity=identity,
            )
            console.print(f"  {section} commander: {principal}")


def configure_multisig_signers(
    multisig_id: str,
    signers: list[str],
    network: str,
    *,
    identity: str | None = None,
    threshold: int = 1,
    expiry_secs: int = 604800,
) -> None:
    signer_vec = "; ".join(f'principal "{s}"' for s in signers)
    arg = f"(vec {{ {signer_vec} }} : vec principal, {threshold} : nat, {expiry_secs} : nat)"
    raw = dfx.canister_call(
        multisig_id,
        "configure",
        arg,
        network,
        identity=identity,
    )
    text = raw.strip().lower()
    if "ok" in text or "already configured" in text:
        console.print(f"  multisig configured: {threshold}-of-{len(signers)} signers")
        return
    raise RuntimeError(f"multisig configure failed: {raw}")
