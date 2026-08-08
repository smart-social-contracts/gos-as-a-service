"""Seed Casals conductor orchestra: templates, authorized WASMs, sheet, multisig."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from rich.console import Console

from gaas import dfx
from gaas.descriptor import Descriptor
from gaas.file_registry_client import fetch_namespace_hashes, upload_file
from gaas.platform import find_local_assetstorage_wasm, resolve_casals_src
from gaas.versions import resolve_deploy_version

console = Console()

CASALS_TEMPLATES_NAMESPACE = "casals-templates"

# Latest orchestration template versions from Casals seed/templates.json.
ORCHESTRATION_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    ("orchestration-baton", "1.3.0", "orchestration-baton@1.3.0.wasm.gz"),
    ("orchestration-multisig", "1.1.0", "orchestration-multisig@1.1.0.wasm.gz"),
)


def platform_sheet() -> dict[str, Any]:
    """Minimal sheet: Infra/governance/multisig + empty Deployments section."""
    return {
        "name": "gaas-platform",
        "description": (
            "GaaS platform orchestra: governance multisig in Infra; "
            "realm stands created by the installer in Deployments at deploy time."
        ),
        "sections": [
            {
                "name": "Infra",
                "description": "Platform orchestration governance (multisig only).",
                "stands": [
                    {
                        "name": "governance",
                        "description": "Root multisig for platform and baton IC control.",
                        "canisters": [
                            {
                                "name": "multisig",
                                "wasm_key": "orchestration-multisig",
                                "kind": "backend",
                            }
                        ],
                    }
                ],
            },
            {
                "name": "Deployments",
                "description": "Realm stands (one per realm; created by realm_installer).",
                "stands": [],
            },
        ],
    }


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
        console.print("  building orchestration templates (Motoko/basilisk)...")
        subprocess.run(["bash", str(script)], cwd=casals_root, check=True)
    if not path.is_file():
        raise RuntimeError(
            f"missing orchestration template {path}; "
            "run `make build-templates` in the Casals checkout"
        )
    return path


def _gunzip_bytes(path: Path) -> bytes:
    with gzip.open(path, "rb") as handle:
        return handle.read()


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
    casals_root = resolve_casals_src(casals_src)
    if casals_root is None:
        raise RuntimeError(
            "orchestration templates require a Casals checkout "
            "(--casals-src, CASALS_SRC, or /srv/dev/Casals)"
        )

    existing = list_authorized_keys(casals_id, network, identity=identity)
    for family, version, filename in ORCHESTRATION_TEMPLATES:
        key = f"{family}@{version}"
        registry_path = key.replace("@", "@") + ".wasm" if "@" in filename else f"{family}.wasm"
        if family == "orchestration-baton":
            registry_path = "orchestration-baton@1.3.0.wasm"
        elif family == "orchestration-multisig":
            registry_path = "orchestration-multisig@1.1.0.wasm"

        gz_path = _resolve_template_wasm(casals_root, filename)
        wasm_bytes = _gunzip_bytes(gz_path)
        digest = hashlib.sha256(wasm_bytes).hexdigest()
        if existing.get(key) == digest:
            console.print(f"  {key}: already authorized")
            continue

        console.print(f"  uploading + authorizing {key}...")
        _upload_wasm_to_registry(
            registry_id,
            CASALS_TEMPLATES_NAMESPACE,
            registry_path,
            wasm_bytes,
            network,
            identity=identity,
        )
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
) -> None:
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
    backend_key = f"{entry.artifacts.backend_wasm_key}@{version}"
    if existing.get(backend_key) != backend_hash:
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
                "wasm_type": "basilisk",
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

    The sheet format has no commander syntax, so this runs as a separate
    set_commander call. Section commander permissions cascade to stands, and
    set_commander adds-or-updates without removing others, so this is safely
    idempotent.
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
