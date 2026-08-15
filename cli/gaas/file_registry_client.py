"""Upload helpers for the file_registry canister."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tarfile
import tempfile
from pathlib import Path

from gaas import dfx

CHUNK_SIZE = 64 * 1024
FINALIZE_BATCH = 8


# Keep in sync with CONTENT_TYPES in src/file_registry/main.py (gaas file_registry
# canister). Wrong types here are copied into registry metadata and then into realm
# frontend asset canisters by Casals bundle upload (realms#292).
_CONTENT_TYPE_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".json5", "application/json"),
    (".json", "application/json"),
    (".js", "application/javascript"),
    (".mjs", "application/javascript"),
    (".css", "text/css"),
    (".html", "text/html"),
    (".wasm.gz", "application/wasm"),
    (".wasm", "application/wasm"),
    (".svg", "image/svg+xml"),
    (".png", "image/png"),
    (".jpg", "image/jpeg"),
    (".jpeg", "image/jpeg"),
    (".gif", "image/gif"),
    (".ico", "image/x-icon"),
    (".webp", "image/webp"),
    (".txt", "text/plain"),
    (".md", "text/markdown"),
    (".ts", "text/plain"),
    (".toml", "text/plain"),
    (".yaml", "text/plain"),
    (".yml", "text/plain"),
    (".svelte", "text/plain"),
    (".woff2", "font/woff2"),
    (".woff", "font/woff"),
    (".ttf", "font/ttf"),
    (".webmanifest", "application/manifest+json"),
)


def _content_type(path: str) -> str:
    lower = path.lower()
    for suffix, content_type in _CONTENT_TYPE_SUFFIXES:
        if lower.endswith(suffix):
            return content_type
    return "application/octet-stream"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_namespace_hashes(
    registry_id: str,
    namespace: str,
    network: str,
    *,
    identity: str | None = None,
) -> dict[str, str]:
    try:
        raw = dfx.canister_call(
            registry_id,
            "list_files",
            dfx.candid_text_arg(json.dumps({"namespace": namespace})),
            network,
            identity=identity,
            query=True,
        )
        files = json.loads(raw)
        if isinstance(files, list):
            return {item["path"]: item.get("sha256", "") for item in files}
    except (json.JSONDecodeError, dfx.DfxError, KeyError):
        pass
    return {}


def namespace_published(
    registry_id: str,
    namespace: str,
    network: str,
    *,
    identity: str | None = None,
) -> bool:
    try:
        raw = dfx.canister_call(
            registry_id,
            "list_namespaces",
            dfx.candid_text_arg(""),
            network,
            identity=identity,
            query=True,
        )
        entries = json.loads(raw)
        for entry in entries:
            if entry.get("namespace") == namespace:
                return True
    except (json.JSONDecodeError, dfx.DfxError):
        pass
    return False


def delete_file(
    registry_id: str,
    namespace: str,
    registry_path: str,
    network: str,
    *,
    identity: str | None = None,
) -> bool:
    payload = json.dumps({"namespace": namespace, "path": registry_path})
    raw = dfx.canister_call(
        registry_id,
        "delete_file",
        dfx.candid_text_arg(payload),
        network,
        identity=identity,
    )
    try:
        result = json.loads(raw)
        return isinstance(result, dict) and result.get("ok") is True
    except json.JSONDecodeError:
        return False


def upload_file(
    registry_id: str,
    namespace: str,
    registry_path: str,
    local_path: Path,
    network: str,
    *,
    identity: str | None = None,
    existing_hashes: dict[str, str] | None = None,
) -> str:
    """Return uploaded, skipped, or failed."""
    size = local_path.stat().st_size
    if size == 0:
        return "failed"

    if existing_hashes and registry_path in existing_hashes:
        if existing_hashes[registry_path] == sha256_file(local_path):
            return "skipped"
        delete_file(registry_id, namespace, registry_path, network, identity=identity)
    total_chunks = max(1, (size + CHUNK_SIZE - 1) // CHUNK_SIZE)
    content_type = _content_type(registry_path)

    with local_path.open("rb") as handle:
        for chunk_index in range(total_chunks):
            blob = handle.read(CHUNK_SIZE)
            payload = json.dumps(
                {
                    "namespace": namespace,
                    "path": registry_path,
                    "chunk_index": chunk_index,
                    "total_chunks": total_chunks,
                    "data_b64": base64.b64encode(blob).decode("ascii"),
                    "content_type": content_type,
                }
            )
            raw = dfx.canister_call(
                registry_id,
                "store_file_chunk",
                dfx.candid_text_arg(payload),
                network,
                identity=identity,
                timeout=600,
            )
            result = json.loads(raw)
            if not (isinstance(result, dict) and result.get("ok") is True):
                return "failed"

    local_sha = sha256_file(local_path)
    while True:
        finalize_payload = json.dumps(
            {
                "namespace": namespace,
                "path": registry_path,
                "expected_sha256": local_sha,
                "batch_size": FINALIZE_BATCH,
            }
        )
        raw = dfx.canister_call(
            registry_id,
            "finalize_chunked_file_step",
            dfx.candid_text_arg(finalize_payload),
            network,
            identity=identity,
            timeout=600,
        )
        result = json.loads(raw)
        if not (isinstance(result, dict) and result.get("ok") is True):
            return "failed"
        if result.get("done") is True:
            return "uploaded"


def publish_namespace(
    registry_id: str,
    namespace: str,
    network: str,
    *,
    identity: str | None = None,
) -> None:
    raw = dfx.canister_call(
        registry_id,
        "publish_namespace",
        dfx.candid_text_arg(json.dumps({"namespace": namespace})),
        network,
        identity=identity,
        timeout=120,
    )
    result = json.loads(raw)
    if not (isinstance(result, dict) and result.get("ok") is True):
        raise RuntimeError(f"publish_namespace({namespace}) failed: {result}")


def set_namespace_approval(
    registry_id: str,
    namespace: str,
    network: str,
    *,
    identity: str | None = None,
    status: str = "approved",
    notes: str = "",
) -> None:
    """Record marketplace approval for a namespace (caller becomes approver)."""
    payload = json.dumps({"namespace": namespace, "status": status, "notes": notes})
    raw = dfx.canister_call(
        registry_id,
        "set_namespace_approval",
        dfx.candid_text_arg(payload),
        network,
        identity=identity,
        timeout=120,
    )
    result = json.loads(raw)
    if not (isinstance(result, dict) and result.get("ok") is True):
        raise RuntimeError(f"set_namespace_approval({namespace}) failed: {result}")


def approve_marketplace_namespaces(
    registry_id: str,
    namespaces: list[str],
    network: str,
    *,
    identity: str | None = None,
) -> None:
    """Approve codex/extension namespaces after seeding."""
    for namespace in sorted(set(namespaces)):
        if not (namespace.startswith("ext/") or namespace.startswith("codex/")):
            continue
        set_namespace_approval(
            registry_id,
            namespace,
            network,
            identity=identity,
        )


def extract_frontend_tar(tar_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as archive:
        archive.extractall(dest)
    return dest


def upload_directory(
    registry_id: str,
    namespace: str,
    dist_dir: Path,
    network: str,
    *,
    identity: str | None = None,
    existing_hashes: dict[str, str] | None = None,
) -> tuple[int, int]:
    uploaded = 0
    failed = 0
    for root, _dirs, files in os.walk(dist_dir):
        for fname in sorted(files):
            local = Path(root) / fname
            rel = local.relative_to(dist_dir).as_posix()
            result = upload_file(
                registry_id,
                namespace,
                rel,
                local,
                network,
                identity=identity,
                existing_hashes=existing_hashes,
            )
            if result == "failed":
                failed += 1
            elif result == "uploaded":
                uploaded += 1
    return uploaded, failed


def seed_gos_entry(
    registry_id: str,
    backend_ns: str,
    frontend_ns: str,
    backend_asset_path: Path,
    frontend_source: Path,
    network: str,
    *,
    identity: str | None = None,
) -> None:
    backend_hashes = fetch_namespace_hashes(registry_id, backend_ns, network, identity=identity)
    backend_path = backend_asset_path.name
    if upload_file(
        registry_id,
        backend_ns,
        backend_path,
        backend_asset_path,
        network,
        identity=identity,
        existing_hashes=backend_hashes,
    ) == "failed":
        raise RuntimeError(f"failed uploading {backend_ns}/{backend_path}")

    if frontend_source.is_file() and frontend_source.name.endswith(".tar.gz"):
        with tempfile.TemporaryDirectory(prefix="gaas-fe-") as tmp:
            dist = extract_frontend_tar(frontend_source, Path(tmp))
            frontend_hashes = fetch_namespace_hashes(
                registry_id, frontend_ns, network, identity=identity
            )
            _uploaded, failed = upload_directory(
                registry_id,
                frontend_ns,
                dist,
                network,
                identity=identity,
                existing_hashes=frontend_hashes,
            )
            if failed:
                raise RuntimeError(f"frontend upload had {failed} failures for {frontend_ns}")
    else:
        frontend_hashes = fetch_namespace_hashes(
            registry_id, frontend_ns, network, identity=identity
        )
        _uploaded, failed = upload_directory(
            registry_id,
            frontend_ns,
            frontend_source,
            network,
            identity=identity,
            existing_hashes=frontend_hashes,
        )
        if failed:
            raise RuntimeError(f"frontend upload had {failed} failures for {frontend_ns}")

    publish_namespace(registry_id, backend_ns, network, identity=identity)
    publish_namespace(registry_id, frontend_ns, network, identity=identity)


def _parse_upgrade_result(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("("):
        raw = raw[1:-1].strip() if raw.endswith(")") else raw[1:].strip()
    if "Ok = " in raw:
        inner = raw.split("Ok = ", 1)[1].rstrip(" })").strip()
        if inner.startswith('"') and inner.endswith('"'):
            inner = inner[1:-1].replace('\\"', '"')
        return json.loads(inner)
    if "Err = " in raw:
        err = raw.split("Err = ", 1)[1].rstrip(" })").strip('"')
        raise RuntimeError(f"publish_version failed: {err}")
    return json.loads(raw)


def list_catalog_versions(
    registry_backend_id: str,
    network: str,
    *,
    identity: str | None = None,
) -> set[str]:
    try:
        raw = dfx.canister_call(
            registry_backend_id,
            "list_versions",
            dfx.candid_text_arg(""),
            network,
            identity=identity,
            query=True,
        )
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("success") and isinstance(data.get("versions"), list):
            return {
                str(item.get("version", "")).strip()
                for item in data["versions"]
                if item.get("version")
            }
    except (json.JSONDecodeError, dfx.DfxError, RuntimeError):
        pass
    return set()


def ensure_version_catalog_entry(
    registry_backend_id: str,
    file_registry_id: str,
    version: str,
    backend_ns: str,
    frontend_ns: str,
    backend_path: str,
    backend_hash: str,
    network: str,
    *,
    identity: str | None = None,
) -> str:
    """Publish a GOS version to the registry catalog if not already listed.

    Returns ``published``, ``skipped``, or ``failed``.
    """
    if version in list_catalog_versions(registry_backend_id, network, identity=identity):
        return "skipped"

    payload = json.dumps(
        {
            "version": version,
            "backend_wasm_url": f"fileregistry://{file_registry_id}/{backend_ns}/{backend_path}",
            "frontend_tar_url": f"fileregistry://{file_registry_id}/{frontend_ns}",
            "backend_wasm_hash": backend_hash,
            "frontend_tar_hash": "",
        }
    )
    raw = dfx.canister_call(
        registry_backend_id,
        "publish_version",
        dfx.candid_text_arg(payload),
        network,
        identity=identity,
        timeout=120,
    )
    result = _parse_upgrade_result(raw)
    if result.get("success"):
        return "published"
    raise RuntimeError(f"publish_version({version}) failed: {result}")
