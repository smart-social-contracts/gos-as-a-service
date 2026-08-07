"""
File Registry — on-chain file store for realm layer objects

Generic file registry canister for storage of:
  - Base realm WASM (Layer 1):      namespace "wasm", path "realm-base-{version}.wasm"
  - Extensions (Layer 2):           namespace "ext/{ext_id}/{version}", paths under backend/ and frontend/
  - Codices (Layer 3):              namespace "codex/{codex_id}/{version}", paths *.py

Inherits all base file registry functionality:
  - HTTP serving with CORS (browser fetch / script src)
  - Inter-canister Candid query API
  - Per-namespace publisher ACL
  - Chunked upload for files > 1 MB

Additional endpoints:
  - list_extensions / list_codices      — convention-aware listing
  - latest_version                      — resolve latest semver for an extension or codex
  - get_backend_files                   — return all backend files for an extension/codex (for realm pull)
  - get_extension_manifest              — return manifest.json for a specific extension version

Storage layout (persistent filesystem, survives upgrades):
  /registry/_namespaces.json        index of all namespaces
  /registry/_acl.json               {namespace: [principal_str, ...]}
  /registry/{namespace}/_meta.json  {files: {path: {size, content_type, sha256, updated}}}
  /registry/{namespace}/{path}      actual file content
  /registry/_chunks/                temporary chunk staging area

Refs: https://github.com/smart-social-contracts/realms/issues/168
"""

import base64
import hashlib
import json
import os
from typing import Tuple

from basilisk import (
    blob,
    ic,
    nat16,
    Opt,
    Principal,
    query,
    Record,
    text,
    update,
    Vec,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGISTRY_DIR = "/registry"
CHUNKS_DIR = "/registry/_chunks"
NAMESPACES_FILE = "/registry/_namespaces.json"
ACL_FILE = "/registry/_acl.json"

CONTENT_TYPES = {
    ".py":   "text/plain",
    ".js":   "application/javascript",
    ".mjs":  "application/javascript",
    ".json": "application/json",
    ".html": "text/html",
    ".css":  "text/css",
    ".wasm": "application/wasm",
    ".txt":  "text/plain",
    ".md":   "text/markdown",
    ".svg":  "image/svg+xml",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif":  "image/gif",
    ".ico":  "image/x-icon",
    ".ts":   "text/plain",
    ".toml": "text/plain",
    ".yaml": "text/plain",
    ".yml":  "text/plain",
    ".svelte": "text/plain",
}

# Namespace prefixes for convention-based queries
NS_PREFIX_EXT = "ext/"
NS_PREFIX_CODEX = "codex/"
NS_PREFIX_WASM = "wasm"

# ---------------------------------------------------------------------------
# HTTP types (for the http_request query endpoint)
# ---------------------------------------------------------------------------

Header = Tuple[str, str]


class HttpRequest(Record):
    method: str
    url: str
    headers: Vec["Header"]
    body: blob


class HttpResponseIncoming(Record):
    status_code: nat16
    headers: Vec["Header"]
    body: blob
    streaming_strategy: Opt[str]
    upgrade: Opt[bool]


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _ensure_dirs():
    os.makedirs(REGISTRY_DIR, exist_ok=True)
    os.makedirs(CHUNKS_DIR, exist_ok=True)


def _file_path(namespace: str, path: str) -> str:
    return os.path.join(REGISTRY_DIR, namespace, path.lstrip("/"))


def _meta_path(namespace: str) -> str:
    return os.path.join(REGISTRY_DIR, namespace, "_meta.json")


def _load_namespaces() -> dict:
    try:
        with open(NAMESPACES_FILE, "r") as f:
            return json.loads(f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_namespaces(ns: dict):
    _ensure_dirs()
    with open(NAMESPACES_FILE, "w") as f:
        f.write(json.dumps(ns))


def _load_acl() -> dict:
    try:
        with open(ACL_FILE, "r") as f:
            return json.loads(f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_acl(acl: dict):
    _ensure_dirs()
    with open(ACL_FILE, "w") as f:
        f.write(json.dumps(acl))


def _load_meta(namespace: str) -> dict:
    try:
        with open(_meta_path(namespace), "r") as f:
            return json.loads(f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"files": {}}


def _save_meta(namespace: str, meta: dict):
    ns_dir = os.path.join(REGISTRY_DIR, namespace)
    os.makedirs(ns_dir, exist_ok=True)
    with open(_meta_path(namespace), "w") as f:
        f.write(json.dumps(meta))


def _guess_content_type(path: str) -> str:
    for ext, ct in CONTENT_TYPES.items():
        if path.endswith(ext):
            return ct
    return "application/octet-stream"


def _ensure_namespace_exists(namespace: str, caller_str: str):
    namespaces = _load_namespaces()
    if namespace not in namespaces:
        namespaces[namespace] = {
            "namespace": namespace,
            "created": ic.time(),
            "owner": caller_str,
            "description": "",
            "published": False,
        }
        _save_namespaces(namespaces)


def _is_published(ns_info: dict) -> bool:
    """Check whether a namespace is published.

    Legacy namespaces without a 'published' key are treated as published.
    The 'wasm' namespace (non-versioned) is always considered published.
    """
    return ns_info.get("published", True)


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def _parse_semver(version_str: str) -> tuple:
    """Parse a semver string into a comparable tuple, e.g. '1.2.3' -> (1, 2, 3)."""
    try:
        parts = version_str.split(".")
        return tuple(int(p) for p in parts)
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _find_latest_version(namespaces: dict, prefix: str) -> str:
    """Find the highest semver among *published* namespaces matching a prefix.

    E.g. prefix="ext/voting/" scans "ext/voting/1.0.0", "ext/voting/1.0.3" -> "1.0.3"
    Unpublished namespaces are skipped so that partially-uploaded versions
    are never resolved as 'latest'.
    """
    best_version = ""
    best_tuple = (-1,)
    for ns_name, ns_info in namespaces.items():
        if ns_name.startswith(prefix) and _is_published(ns_info):
            version = ns_name[len(prefix):]
            if "/" in version:
                continue
            vt = _parse_semver(version)
            if vt > best_tuple:
                best_tuple = vt
                best_version = version
    return best_version


def _published_versions(namespaces: dict, prefix: str) -> list:
    """All published versions under a prefix, e.g. ['1.0.0', '1.1.2']."""
    versions = []
    for ns_name, ns_info in namespaces.items():
        if ns_name.startswith(prefix) and _is_published(ns_info):
            version = ns_name[len(prefix):]
            if "/" not in version:
                versions.append(version)
    return versions


def _spec_matches(spec: str, version: str) -> bool:
    """Does *version* satisfy a pin spec? (issue #242 — codex-as-distro pins)

    Supported specs:
      - exact:   "1.2.3"
      - wildcard: "1.2.x", "1.x", "1.2.*"
      - caret:   "^1.2.3" (same major, >= spec)
      - tilde:   "~1.2.3" (same major.minor, >= spec)
    """
    spec = (spec or "").strip()
    vt = _parse_semver(version)

    if spec.startswith("^") or spec.startswith("~"):
        base = _parse_semver(spec[1:])
        if vt < base:
            return False
        if vt[0] != base[0]:
            return False
        if spec.startswith("~") and (len(vt) < 2 or len(base) < 2 or vt[1] != base[1]):
            return False
        return True

    if "x" in spec.lower() or "*" in spec:
        spec_parts = spec.replace("*", "x").lower().split(".")
        version_parts = version.split(".")
        for i, sp in enumerate(spec_parts):
            if sp == "x":
                return True
            if i >= len(version_parts) or sp != version_parts[i]:
                return False
        return len(spec_parts) == len(version_parts)

    return spec == version


def _is_range_spec(spec: str) -> bool:
    s = (spec or "").strip().lower()
    return s.startswith(("^", "~")) or "x" in s.split(".") or "*" in s


def _resolve_version_spec(namespaces: dict, prefix: str, spec: str) -> str:
    """Resolve a version spec to a concrete published version.

    Empty / "latest" resolves to the highest published version; range specs
    resolve to the highest published match; exact versions pass through
    (existence is checked by the caller). Returns "" when nothing matches.
    """
    spec = (spec or "").strip()
    if not spec or spec.lower() == "latest":
        return _find_latest_version(namespaces, prefix)
    if not _is_range_spec(spec):
        return spec
    best = ""
    best_tuple = (-1,)
    for version in _published_versions(namespaces, prefix):
        if _spec_matches(spec, version):
            vt = _parse_semver(version)
            if vt > best_tuple:
                best_tuple = vt
                best = version
    return best


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

def _require_controller() -> str | None:
    if not ic.is_controller(ic.caller()):
        return json.dumps({"error": "Unauthorized: caller is not a controller"})
    return None


def _require_publisher(namespace: str) -> str | None:
    if ic.is_controller(ic.caller()):
        return None
    caller = ic.caller().to_str()
    acl = _load_acl()
    ns_acl = acl.get(namespace, [])
    if caller in ns_acl:
        return None
    # Auto-grant: first authenticated caller to a new namespace becomes its publisher
    if not ns_acl:
        acl[namespace] = [caller]
        _save_acl(acl)
        return None
    return json.dumps({"error": f"Unauthorized: not a publisher for namespace '{namespace}'"})


# Curated-publishers ACL key for privileged package classifications. A codex
# is a privileged system extension (issue #244): only controllers and
# principals on this list may publish a manifest declaring "kind": "codex"
# (or the "codex/" legacy namespace) — an arbitrary marketplace upload must
# not be able to claim codex powers.
CODEX_CURATORS_ACL_KEY = "_codex_curators"


def _require_codex_curator() -> str | None:
    if ic.is_controller(ic.caller()):
        return None
    caller = ic.caller().to_str()
    acl = _load_acl()
    if caller in acl.get(CODEX_CURATORS_ACL_KEY, []):
        return None
    return json.dumps({
        "error": (
            "Unauthorized: publishing a codex package (kind: codex) requires "
            "codex-curator rights on this registry"
        )
    })


def _codex_manifest_gate(namespace: str, path: str, content: bytes) -> str | None:
    """Reject uncurated uploads that claim the privileged codex classification.

    Applies to any manifest.json declaring ``"kind": "codex"`` and to all
    writes under the legacy ``codex/`` namespace.
    """
    if namespace.startswith(NS_PREFIX_CODEX):
        return _require_codex_curator()
    if path.split("/")[-1] != "manifest.json":
        return None
    try:
        manifest = json.loads(content.decode("utf-8"))
    except Exception:
        return None
    if isinstance(manifest, dict) and manifest.get("kind") == "codex":
        return _require_codex_curator()
    return None


# ---------------------------------------------------------------------------
# Base query endpoints
# ---------------------------------------------------------------------------

@query
def list_namespaces() -> text:
    """Return JSON list of all namespaces with file counts and sizes."""
    namespaces = _load_namespaces()
    result = []
    for ns_name, ns_info in namespaces.items():
        meta = _load_meta(ns_name)
        files = meta.get("files", {})
        total_bytes = sum(f.get("size", 0) for f in files.values())
        result.append({
            "namespace": ns_name,
            "file_count": len(files),
            "total_bytes": total_bytes,
            "created": ns_info.get("created", 0),
            "owner": ns_info.get("owner", ""),
            "description": ns_info.get("description", ""),
        })
    result.sort(key=lambda x: x["namespace"])
    return json.dumps(result)


@query
def list_files(args: text) -> text:
    """Return JSON list of files in a namespace.

    Args (JSON): {"namespace": str}

    Returns ``"[]"`` for an unknown / partial namespace prefix (callers
    typically iterate prefixes during exploration). Returns
    ``{"error": "..."}`` only for genuinely malformed JSON input — never
    traps, so HTTP and UI callers can probe freely.
    """
    try:
        params = json.loads(args) if args else {}
    except (json.JSONDecodeError, ValueError) as e:
        return json.dumps({"error": f"invalid args (not JSON): {e}"})
    if not isinstance(params, dict) or "namespace" not in params:
        return json.dumps({"error": "expected JSON object with 'namespace' field"})
    namespace = params["namespace"]
    namespaces = _load_namespaces()
    if namespace not in namespaces:
        return "[]"
    meta = _load_meta(namespace)
    files = meta.get("files", {})
    result = [
        {
            "path": path,
            "size": info.get("size", 0),
            "content_type": info.get("content_type", "application/octet-stream"),
            "sha256": info.get("sha256", ""),
            "updated": info.get("updated", 0),
        }
        for path, info in files.items()
    ]
    result.sort(key=lambda x: x["path"])
    return json.dumps(result)


@query
def get_file(args: text) -> text:
    """Return file content as base64 + metadata.

    Args (JSON): {"namespace": str, "path": str}
    Returns JSON: {"content_b64": str, "content_type": str, "size": int, "sha256": str}
    """
    params = json.loads(args)
    namespace = params["namespace"]
    path = params["path"].lstrip("/")
    fp = _file_path(namespace, path)
    try:
        with open(fp, "rb") as f:
            content = f.read()
    except FileNotFoundError:
        return json.dumps({"error": f"Not found: {namespace}/{path}"})

    meta = _load_meta(namespace)
    file_info = meta.get("files", {}).get(path, {})
    return json.dumps({
        "content_b64": base64.b64encode(content).decode("ascii"),
        "content_type": file_info.get("content_type") or _guess_content_type(path),
        "size": len(content),
        "sha256": file_info.get("sha256") or hashlib.sha256(content).hexdigest(),
    })


@query
def get_file_size(args: text) -> text:
    """Return the byte size of a stored file.

    Used by the realm_installer canister (Motoko) to know how many
    chunks it needs to pull when assembling a base WASM that is too
    large (~3-15 MB) to fit in a single inter-canister message
    (~2 MiB Candid encoding budget).

    Args (JSON): {"namespace": str, "path": str}
    Returns JSON: {"size": int, "content_type": str, "sha256": str}
                  | {"error": str}
    """
    params = json.loads(args)
    namespace = params["namespace"]
    path = params["path"].lstrip("/")

    fp = _file_path(namespace, path)
    try:
        size = os.path.getsize(fp)
    except FileNotFoundError:
        return json.dumps({"error": f"Not found: {namespace}/{path}"})

    meta = _load_meta(namespace)
    file_info = meta.get("files", {}).get(path, {})
    return json.dumps({
        "size": size,
        "content_type": file_info.get("content_type") or _guess_content_type(path),
        "sha256": file_info.get("sha256", ""),
    })


# Maximum chunk size the chunked-read API will return per call.
# Per-chunk read size for inter-canister chunk fetches. Dropped from
# 768 KB → 128 KB because base64-encoding the slice in WASI Python costs
# ~30M instructions per 100 KB; at 768 KB per call we blow the 40B
# per-message instruction budget. Smaller chunks → more round-trips but
# each call stays well under budget.
_MAX_CHUNK_READ_BYTES = 128 * 1024


@query
def get_file_chunk(args: text) -> text:
    """Return a slice of a stored file as base64.

    Args (JSON): {
        "namespace": str,
        "path": str,
        "offset": int,                 (byte offset, default 0)
        "length": int                  (bytes to read; capped to ~768KB)
    }
    Returns JSON: {
        "content_b64": str,            (base64 of the slice)
        "offset": int,
        "length": int,                 (actual bytes returned)
        "total_size": int,
        "eof": bool
    } | {"error": str}

    Used by realm_installer to pull a multi-MB realm-base WASM from the
    registry one chunk at a time before calling the IC management
    canister's `install_chunked_code`.
    """
    params = json.loads(args)
    namespace = params["namespace"]
    path = params["path"].lstrip("/")
    offset = int(params.get("offset", 0))
    length = int(params.get("length", _MAX_CHUNK_READ_BYTES))
    if length <= 0 or length > _MAX_CHUNK_READ_BYTES:
        length = _MAX_CHUNK_READ_BYTES

    fp = _file_path(namespace, path)
    try:
        size = os.path.getsize(fp)
    except FileNotFoundError:
        return json.dumps({"error": f"Not found: {namespace}/{path}"})

    if offset < 0 or offset > size:
        return json.dumps({"error": f"Offset {offset} out of range (size={size})"})

    with open(fp, "rb") as f:
        f.seek(offset)
        chunk = f.read(length)

    return json.dumps({
        "content_b64": base64.b64encode(chunk).decode("ascii"),
        "offset": offset,
        "length": len(chunk),
        "total_size": size,
        "eof": (offset + len(chunk)) >= size,
    })


@query
def get_file_chunk_icc(
    namespace: text, path: text, offset: text, length: text
) -> text:
    """Inter-canister variant of get_file_chunk.

    Basilisk's Candid encoder treats `{}` as record syntax, so cross-canister
    calls cannot pass JSON dict strings reliably. This endpoint exposes the
    same logic with positional text arguments. `offset` and `length` are
    decimal strings parsed to int; pass "0"/"" for length to use default.
    """
    try:
        off = int(offset) if offset else 0
        ln = int(length) if length else _MAX_CHUNK_READ_BYTES
    except (TypeError, ValueError):
        return json.dumps({"error": "offset and length must be integers"})

    return get_file_chunk(json.dumps({
        "namespace": namespace,
        "path": path,
        "offset": off,
        "length": ln,
    }))


@query
def get_file_size_icc(namespace: text, path: text) -> text:
    """Inter-canister variant of get_file_size."""
    return get_file_size(json.dumps({"namespace": namespace, "path": path}))


@query
def list_files_icc(namespace: text) -> text:
    """Inter-canister variant of list_files (positional arg).

    Lets a controller canister (e.g. Casals) enumerate a whole namespace's files
    — used to upload an entire frontend bundle into a freshly created asset
    canister — without passing a JSON-dict arg, which Basilisk cannot encode
    reliably across canisters."""
    return list_files(json.dumps({"namespace": namespace}))


@query
def get_stats() -> text:
    """Return overall registry statistics."""
    namespaces = _load_namespaces()
    total_files = 0
    total_bytes = 0
    for ns_name in namespaces:
        meta = _load_meta(ns_name)
        files = meta.get("files", {})
        total_files += len(files)
        total_bytes += sum(f.get("size", 0) for f in files.values())
    return json.dumps({
        "namespaces": len(namespaces),
        "total_files": total_files,
        "total_bytes": total_bytes,
    })


@query
def get_acl() -> text:
    """Return the full publisher ACL: {namespace: [principal_str]}."""
    return json.dumps(_load_acl())


# ---------------------------------------------------------------------------
# Enhanced query endpoints — convention-aware
# ---------------------------------------------------------------------------

@query
def list_extensions() -> text:
    """List all extensions with their available versions.

    Returns JSON: [
        {"ext_id": str, "versions": [str], "latest": str, "manifest": dict|null},
        ...
    ]
    """
    namespaces = _load_namespaces()
    extensions = {}

    for ns_name, ns_info in namespaces.items():
        if not ns_name.startswith(NS_PREFIX_EXT):
            continue
        if not _is_published(ns_info):
            continue
        # Parse "ext/{ext_id}/{version}"
        rest = ns_name[len(NS_PREFIX_EXT):]
        parts = rest.split("/", 1)
        if len(parts) != 2:
            continue
        ext_id, version = parts

        if ext_id not in extensions:
            extensions[ext_id] = {"ext_id": ext_id, "versions": []}
        extensions[ext_id]["versions"].append(version)

    result = []
    for ext_id, info in sorted(extensions.items()):
        info["versions"].sort(key=_parse_semver)
        latest = info["versions"][-1] if info["versions"] else ""
        info["latest"] = latest

        # Try to load manifest from latest version
        manifest = None
        if latest:
            ns = f"{NS_PREFIX_EXT}{ext_id}/{latest}"
            fp = _file_path(ns, "manifest.json")
            try:
                with open(fp, "r") as f:
                    manifest = json.loads(f.read())
            except (FileNotFoundError, json.JSONDecodeError):
                pass
        info["manifest"] = manifest
        result.append(info)

    return json.dumps(result)


def _manifest_declares_codex(ns: str) -> bool:
    """True when a namespace's manifest.json declares ``"kind": "codex"``."""
    fp = _file_path(ns, "manifest.json")
    try:
        with open(fp, "r") as f:
            manifest = json.loads(f.read())
        return isinstance(manifest, dict) and manifest.get("kind") == "codex"
    except Exception:
        return False


@query
def list_codices() -> text:
    """List all codex packages with their available versions.

    Covers both namespace conventions:
      - ``ext/{codex_id}/{version}`` where the manifest declares
        ``"kind": "codex"`` (unified pipeline, issue #244) — preferred;
      - ``codex/{codex_id}/{version}`` (legacy, deprecated).

    Returns JSON: [
        {"codex_id": str, "versions": [str], "latest": str,
         "namespace_prefix": "ext"|"codex"},
        ...
    ]
    """
    namespaces = _load_namespaces()
    codices = {}

    for ns_name, ns_info in namespaces.items():
        if not _is_published(ns_info):
            continue
        if ns_name.startswith(NS_PREFIX_CODEX):
            prefix = "codex"
            rest = ns_name[len(NS_PREFIX_CODEX):]
        elif ns_name.startswith(NS_PREFIX_EXT):
            prefix = "ext"
            rest = ns_name[len(NS_PREFIX_EXT):]
            if not _manifest_declares_codex(ns_name):
                continue
        else:
            continue
        parts = rest.split("/", 1)
        if len(parts) != 2:
            continue
        codex_id, version = parts

        entry = codices.setdefault(
            codex_id, {"codex_id": codex_id, "versions": [], "_prefixes": {}}
        )
        entry["versions"].append(version)
        entry["_prefixes"][version] = prefix

    result = []
    for key, info in sorted(codices.items()):
        info["versions"].sort(key=_parse_semver)
        latest = info["versions"][-1] if info["versions"] else ""
        info["latest"] = latest
        # Namespace prefix of the latest version — what clients should read.
        info["namespace_prefix"] = info.pop("_prefixes").get(latest, "codex")
        result.append(info)

    return json.dumps(result)


@query
def latest_version(args: text) -> text:
    """Resolve the latest version for an extension or codex.

    Args (JSON): {"category": "ext"|"codex", "item_id": str}
      - For extensions: item_id = ext_id (e.g. "voting")
      - For codices: item_id = "realm_type/codex_id" (e.g. "syntropia/membership")

    Returns JSON: {"latest": str, "namespace": str} or {"error": str}
    """
    params = json.loads(args)
    category = params["category"]
    item_id = params["item_id"]

    namespaces = _load_namespaces()

    if category == "ext":
        prefix = f"{NS_PREFIX_EXT}{item_id}/"
    elif category == "codex":
        prefix = f"{NS_PREFIX_CODEX}{item_id}/"
    else:
        return json.dumps({"error": f"Unknown category: {category}. Use 'ext' or 'codex'"})

    version = _find_latest_version(namespaces, prefix)
    if not version:
        return json.dumps({"error": f"No versions found for {category}/{item_id}"})

    return json.dumps({
        "latest": version,
        "namespace": f"{prefix}{version}".rstrip("/"),
    })


@query
def get_extension_manifest(args: text) -> text:
    """Return the manifest.json for a specific extension version.

    Args (JSON): {"ext_id": str, "version": str|null}
      If version is null, resolves to latest.

    Returns JSON: manifest dict or {"error": str}
    """
    params = json.loads(args)
    ext_id = params["ext_id"]
    version = params.get("version")

    namespaces = _load_namespaces()

    if version and str(version).strip().lower() == "latest":
        version = ""

    if not version:
        prefix = f"{NS_PREFIX_EXT}{ext_id}/"
        version = _find_latest_version(namespaces, prefix)
        if not version:
            return json.dumps({"error": f"No versions found for extension '{ext_id}'"})

    ns = f"{NS_PREFIX_EXT}{ext_id}/{version}"
    fp = _file_path(ns, "manifest.json")
    try:
        with open(fp, "r") as f:
            manifest = json.loads(f.read())
        manifest["_version"] = version
        manifest["_namespace"] = ns
        return json.dumps(manifest)
    except FileNotFoundError:
        return json.dumps({"error": f"manifest.json not found in {ns}"})
    except json.JSONDecodeError:
        return json.dumps({"error": f"Invalid JSON in manifest.json for {ns}"})


def _get_backend_files_impl(category: str, item_id: str, version: str) -> str:
    """Shared implementation for get_backend_files and the ICC variant."""
    namespaces = _load_namespaces()

    if category == "ext":
        prefix = f"{NS_PREFIX_EXT}{item_id}/"
    elif category == "codex":
        prefix = f"{NS_PREFIX_CODEX}{item_id}/"
    else:
        return json.dumps({"error": f"Unknown category: {category}"})

    # Resolve the version spec: empty/"latest" → highest published; range pins
    # ("1.2.x", "^1.0.0", "~1.2.3") → highest published match (issue #242).
    resolved = _resolve_version_spec(namespaces, prefix, version or "")
    if not resolved:
        return json.dumps({
            "error": f"No published version of {category}/{item_id} matches '{version or 'latest'}'"
        })
    version = resolved

    ns = f"{prefix}{version}".rstrip("/")

    if ns not in namespaces:
        return json.dumps({"error": f"Namespace '{ns}' not found"})

    if not _is_published(namespaces[ns]):
        return json.dumps({"error": f"Namespace '{ns}' is not yet published"})

    meta = _load_meta(ns)
    all_files = meta.get("files", {})

    files = {}
    for path in all_files:
        if category == "ext":
            if path.startswith("backend/") or path == "manifest.json":
                fp = _file_path(ns, path)
                try:
                    with open(fp, "r") as f:
                        files[path] = f.read()
                except FileNotFoundError:
                    pass
        elif category == "codex":
            fp = _file_path(ns, path)
            try:
                with open(fp, "r") as f:
                    files[path] = f.read()
            except FileNotFoundError:
                pass

    return json.dumps({
        "files": files,
        "version": version,
        "namespace": ns,
        "file_count": len(files),
    })


@query
def get_backend_files(args: text) -> text:
    """Return all backend files for an extension or codex as {filename: content}.

    Args (JSON): {
        "category": "ext"|"codex",
        "item_id": str,
        "version": str|null          (null = latest)
    }
    """
    params = json.loads(args)
    return _get_backend_files_impl(
        params["category"], params["item_id"], params.get("version")
    )


@query
def get_backend_files_icc(category: text, item_id: text, version: text) -> text:
    """Inter-canister variant of get_backend_files with split parameters.

    Basilisk's Candid encoder parses {} as record syntax, so inter-canister
    calls cannot pass JSON strings. This endpoint accepts separate text args.
    Pass empty string for version to get the latest.
    """
    return _get_backend_files_impl(category, item_id, version or None)


def _get_frontend_files_impl(item_id: str, version: str) -> str:
    """Return all frontend/ files for an extension as {path: content}."""
    namespaces = _load_namespaces()
    prefix = f"{NS_PREFIX_EXT}{item_id}/"

    if version and str(version).strip().lower() == "latest":
        version = ""

    if not version:
        version = _find_latest_version(namespaces, prefix)
        if not version:
            return json.dumps({"error": f"No versions found for ext/{item_id}"})

    ns = f"{prefix}{version}".rstrip("/")
    if ns not in namespaces:
        return json.dumps({"error": f"Namespace '{ns}' not found"})
    if not _is_published(namespaces[ns]):
        return json.dumps({"error": f"Namespace '{ns}' is not yet published"})

    meta = _load_meta(ns)
    all_files = meta.get("files", {})

    files = {}
    for path in all_files:
        if path.startswith("frontend/"):
            fp = _file_path(ns, path)
            try:
                with open(fp, "r") as f:
                    files[path] = f.read()
            except FileNotFoundError:
                pass

    return json.dumps({
        "files": files,
        "version": version,
        "namespace": ns,
        "file_count": len(files),
    })


@query
def get_frontend_files(args: text) -> text:
    """Return all frontend files for an extension as {filename: content}."""
    params = json.loads(args)
    return _get_frontend_files_impl(params["item_id"], params.get("version"))


@query
def get_frontend_files_icc(item_id: text, version: text) -> text:
    """Inter-canister variant: return all frontend/ files for an extension."""
    return _get_frontend_files_impl(item_id, version or None)


# ---------------------------------------------------------------------------
# Authenticated update endpoints
# ---------------------------------------------------------------------------

@update
def store_file(args: text) -> text:
    """Store a file. Caller must be a controller or namespace publisher.

    Args (JSON): {
        "namespace": str,
        "path": str,
        "content_b64": str,        (base64-encoded file content)
        "content_type": str        (optional, inferred from extension if absent)
    }
    """
    params = json.loads(args)
    namespace = params["namespace"]
    path = params["path"].lstrip("/")
    content_b64 = params["content_b64"]
    content_type = params.get("content_type") or _guess_content_type(path)

    err = _require_publisher(namespace)
    if err:
        return err

    try:
        content = base64.b64decode(content_b64)
    except Exception as e:
        return json.dumps({"error": f"Invalid base64: {e}"})

    err = _codex_manifest_gate(namespace, path, content)
    if err:
        return err

    caller_str = ic.caller().to_str()
    _ensure_namespace_exists(namespace, caller_str)

    fp = _file_path(namespace, path)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "wb") as f:
        f.write(content)

    sha256 = hashlib.sha256(content).hexdigest()
    meta = _load_meta(namespace)
    meta.setdefault("files", {})[path] = {
        "size": len(content),
        "content_type": content_type,
        "sha256": sha256,
        "updated": ic.time(),
    }
    _save_meta(namespace, meta)

    return json.dumps({
        "ok": True,
        "namespace": namespace,
        "path": path,
        "size": len(content),
        "sha256": sha256,
    })


@update
def delete_file(args: text) -> text:
    """Delete a file. Caller must be a controller or namespace publisher.

    Args (JSON): {"namespace": str, "path": str}
    """
    params = json.loads(args)
    namespace = params["namespace"]
    path = params["path"].lstrip("/")

    err = _require_publisher(namespace)
    if err:
        return err

    fp = _file_path(namespace, path)
    try:
        os.remove(fp)
    except FileNotFoundError:
        return json.dumps({"error": f"Not found: {namespace}/{path}"})

    meta = _load_meta(namespace)
    meta.get("files", {}).pop(path, None)
    _save_meta(namespace, meta)

    return json.dumps({"ok": True, "namespace": namespace, "path": path})


@update
def update_namespace(args: text) -> text:
    """Update namespace description. Controller only.

    Args (JSON): {"namespace": str, "description": str}
    """
    err = _require_controller()
    if err:
        return err

    params = json.loads(args)
    namespace = params["namespace"]
    description = params.get("description", "")

    namespaces = _load_namespaces()
    if namespace not in namespaces:
        return json.dumps({"error": f"Namespace '{namespace}' not found"})

    namespaces[namespace]["description"] = description
    _save_namespaces(namespaces)

    return json.dumps({"ok": True, "namespace": namespace})


@update
def publish_namespace(args: text) -> text:
    """Mark a namespace as published, making it visible to queries.

    Namespaces start unpublished when the first file is stored.
    Call this after all files have been uploaded so that consumers
    (list_extensions, list_codices, latest_version, get_backend_files)
    never see a partially-uploaded version.

    Caller must be a controller or namespace publisher.

    Args (JSON): {"namespace": str}
    Returns JSON: {"ok": true, "namespace": str} or {"error": str}
    """
    params = json.loads(args)
    namespace = params["namespace"]

    err = _require_publisher(namespace)
    if err:
        return err

    namespaces = _load_namespaces()
    if namespace not in namespaces:
        return json.dumps({"error": f"Namespace '{namespace}' not found"})

    namespaces[namespace]["published"] = True
    namespaces[namespace]["published_at"] = ic.time()
    _save_namespaces(namespaces)

    return json.dumps({"ok": True, "namespace": namespace})


@update
def delete_namespace(args: text) -> text:
    """Delete a namespace and all its files. Controller only.

    Args (JSON): {"namespace": str}
    """
    err = _require_controller()
    if err:
        return err

    params = json.loads(args)
    namespace = params["namespace"]

    namespaces = _load_namespaces()
    if namespace not in namespaces:
        return json.dumps({"error": f"Namespace '{namespace}' not found"})

    _delete_namespace_impl(namespace, namespaces)
    _save_namespaces(namespaces)

    return json.dumps({"ok": True, "namespace": namespace})


def _delete_namespace_impl(namespace: str, namespaces: dict) -> int:
    """Delete a namespace's files, meta, and ACL entry. Returns bytes freed."""
    meta = _load_meta(namespace)
    freed = 0
    for path in list(meta.get("files", {}).keys()):
        fp = _file_path(namespace, path)
        try:
            freed += os.path.getsize(fp)
            os.remove(fp)
        except (FileNotFoundError, OSError):
            pass
    try:
        os.remove(_meta_path(namespace))
    except FileNotFoundError:
        pass
    namespaces.pop(namespace, None)
    acl = _load_acl()
    acl.pop(namespace, None)
    _save_acl(acl)
    return freed


def _delete_wasm_file(namespace: str, path: str) -> int:
    """Delete a single file from a namespace. Returns bytes freed."""
    fp = _file_path(namespace, path)
    try:
        size = os.path.getsize(fp)
        os.remove(fp)
        meta = _load_meta(namespace)
        meta.get("files", {}).pop(path, None)
        _save_meta(namespace, meta)
        return size
    except (FileNotFoundError, OSError):
        return 0


@update
def purge_old_versions(args: text) -> text:
    """Delete old versions, keeping only the latest N per extension/codex/assistant.

    Also cleans up old WASM files in the 'wasm' namespace. Controller only.

    Args (JSON): {
        "keep": int           (default 2) — published versions to retain per item
        "dry_run": bool       (default true) — preview without deleting
    }
    Returns JSON: {
        "ok": true,
        "dry_run": bool,
        "deleted_namespaces": [{"namespace": str, "bytes": int}, ...],
        "deleted_wasm_files": [{"path": str, "bytes": int}, ...],
        "kept_namespaces": [str, ...],
        "kept_wasm_files": [str, ...],
        "total_freed_bytes": int,
        "orphaned_chunks_freed_bytes": int
    }
    """
    err = _require_controller()
    if err:
        return err

    params = json.loads(args) if args else {}
    keep = max(1, int(params.get("keep", 2)))
    dry_run = params.get("dry_run", True)

    namespaces = _load_namespaces()

    # ── 1. Group versioned namespaces by (prefix, item_id) ────────────
    # Covers ext/{id}/{ver}, codex/{id}/{ver}, assistant/{id}/{ver}
    VERSIONED_PREFIXES = ("ext/", "codex/", "assistant/")
    groups: dict[str, list[tuple[str, str, dict]]] = {}

    for ns_name, ns_info in namespaces.items():
        for pfx in VERSIONED_PREFIXES:
            if ns_name.startswith(pfx):
                rest = ns_name[len(pfx):]
                parts = rest.split("/", 1)
                if len(parts) == 2:
                    item_id, version = parts
                    group_key = f"{pfx}{item_id}"
                    groups.setdefault(group_key, []).append(
                        (ns_name, version, ns_info)
                    )
                break

    deleted_namespaces = []
    kept_namespaces = []
    total_freed = 0

    for group_key, entries in groups.items():
        published = [(ns, ver, info) for ns, ver, info in entries if _is_published(info)]
        unpublished = [(ns, ver, info) for ns, ver, info in entries if not _is_published(info)]

        published.sort(key=lambda e: _parse_semver(e[1]), reverse=True)
        to_keep = published[:keep]
        to_delete = published[keep:] + unpublished

        for ns, ver, info in to_keep:
            kept_namespaces.append(ns)

        for ns, ver, info in to_delete:
            meta = _load_meta(ns)
            ns_bytes = sum(f.get("size", 0) for f in meta.get("files", {}).values())
            if not dry_run:
                freed = _delete_namespace_impl(ns, namespaces)
                ns_bytes = max(ns_bytes, freed)
            deleted_namespaces.append({"namespace": ns, "bytes": ns_bytes})
            total_freed += ns_bytes

    # ── 2. Clean up old WASM files in the "wasm" namespace ────────────
    deleted_wasm = []
    kept_wasm = []

    if NS_PREFIX_WASM in namespaces:
        meta = _load_meta(NS_PREFIX_WASM)
        wasm_files = list(meta.get("files", {}).keys())

        version_map: dict[str, list[tuple[str, str]]] = {}
        for wf in wasm_files:
            # Parse "realm-base-{version}.wasm" or "realm-base-{version}.wasm.gz"
            if wf.startswith("realm-base-") and ".wasm" in wf:
                after_prefix = wf[len("realm-base-"):]
                if after_prefix.endswith(".wasm.gz"):
                    ver = after_prefix[:-len(".wasm.gz")]
                    key = "realm-base-*.wasm.gz"
                elif after_prefix.endswith(".wasm"):
                    ver = after_prefix[:-len(".wasm")]
                    key = "realm-base-*.wasm"
                else:
                    kept_wasm.append(wf)
                    continue
                version_map.setdefault(key, []).append((wf, ver))
            else:
                kept_wasm.append(wf)

        for key, entries in version_map.items():
            entries.sort(key=lambda e: _parse_semver(e[1]), reverse=True)
            for wf, ver in entries[:keep]:
                kept_wasm.append(wf)
            for wf, ver in entries[keep:]:
                file_info = meta.get("files", {}).get(wf, {})
                wf_bytes = file_info.get("size", 0)
                if not dry_run:
                    freed = _delete_wasm_file(NS_PREFIX_WASM, wf)
                    wf_bytes = max(wf_bytes, freed)
                deleted_wasm.append({"path": wf, "bytes": wf_bytes})
                total_freed += wf_bytes

    # ── 3. Clean up orphaned chunks ───────────────────────────────────
    orphan_freed = 0
    if not dry_run:
        try:
            for entry in os.listdir(CHUNKS_DIR):
                fp = os.path.join(CHUNKS_DIR, entry)
                try:
                    orphan_freed += os.path.getsize(fp)
                    os.remove(fp)
                except OSError:
                    pass
        except FileNotFoundError:
            pass

    if not dry_run:
        _save_namespaces(namespaces)

    return json.dumps({
        "ok": True,
        "dry_run": dry_run,
        "deleted_namespaces": deleted_namespaces,
        "deleted_wasm_files": deleted_wasm,
        "kept_namespaces": sorted(kept_namespaces),
        "kept_wasm_files": sorted(kept_wasm),
        "total_freed_bytes": total_freed,
        "orphaned_chunks_freed_bytes": orphan_freed,
    })


@update
def grant_publish(args: text) -> text:
    """Grant publish access to a principal for a namespace. Controller only.

    Args (JSON): {"namespace": str, "principal": str}
    """
    err = _require_controller()
    if err:
        return err

    params = json.loads(args)
    namespace = params["namespace"]
    principal = params["principal"]

    acl = _load_acl()
    ns_acl = acl.setdefault(namespace, [])
    if principal not in ns_acl:
        ns_acl.append(principal)
        _save_acl(acl)

    return json.dumps({"ok": True, "namespace": namespace, "principal": principal})


@update
def revoke_publish(args: text) -> text:
    """Revoke publish access from a principal for a namespace. Controller only.

    Args (JSON): {"namespace": str, "principal": str}
    """
    err = _require_controller()
    if err:
        return err

    params = json.loads(args)
    namespace = params["namespace"]
    principal = params["principal"]

    acl = _load_acl()
    ns_acl = acl.get(namespace, [])
    if principal in ns_acl:
        ns_acl.remove(principal)
        _save_acl(acl)

    return json.dumps({"ok": True, "namespace": namespace, "principal": principal})


# ---------------------------------------------------------------------------
# Chunked upload — for files > 1 MB (e.g. WASMs)
# ---------------------------------------------------------------------------

def _chunk_file_path(namespace: str, path: str, chunk_index: int) -> str:
    safe_key = f"{namespace}__{path.replace('/', '__')}"
    return os.path.join(CHUNKS_DIR, f"{safe_key}_{chunk_index:04d}")


def _pending_meta_path(namespace: str, path: str) -> str:
    safe_key = f"{namespace}__{path.replace('/', '__')}"
    return os.path.join(CHUNKS_DIR, f"{safe_key}__pending.json")


@update
def store_file_chunk(args: text) -> text:
    """Upload one chunk of a large file.

    Args (JSON): {
        "namespace": str,
        "path": str,
        "chunk_index": int,
        "total_chunks": int,
        "data_b64": str,
        "content_type": str   (optional)
    }
    """
    params = json.loads(args)
    namespace = params["namespace"]
    path = params["path"].lstrip("/")
    chunk_index = int(params["chunk_index"])
    total_chunks = int(params["total_chunks"])
    data_b64 = params["data_b64"]
    content_type = params.get("content_type") or _guess_content_type(path)

    err = _require_publisher(namespace)
    if err:
        return err

    try:
        data = base64.b64decode(data_b64)
    except Exception as e:
        return json.dumps({"error": f"Invalid base64: {e}"})

    _ensure_dirs()
    with open(_chunk_file_path(namespace, path, chunk_index), "wb") as f:
        f.write(data)

    pending_path = _pending_meta_path(namespace, path)
    try:
        with open(pending_path, "r") as f:
            pending = json.loads(f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        pending = {"total_chunks": total_chunks, "uploaded": [], "content_type": content_type}

    if chunk_index not in pending["uploaded"]:
        pending["uploaded"].append(chunk_index)
    with open(pending_path, "w") as f:
        f.write(json.dumps(pending))

    return json.dumps({
        "ok": True,
        "chunk_index": chunk_index,
        "uploaded": len(pending["uploaded"]),
        "total_chunks": total_chunks,
    })


@update
def finalize_chunked_file(args: text) -> text:
    """Assemble previously uploaded chunks into the final file.

    All-in-one variant: concatenates every chunk and computes the SHA-256
    in a single update message. Suitable for files up to ~600 KB on the
    WASI Python runtime; larger files exceed the 40B-instruction
    per-message budget — use ``finalize_chunked_file_step`` for those.

    Args (JSON): {"namespace": str, "path": str}
    """
    params = json.loads(args)
    namespace = params["namespace"]
    path = params["path"].lstrip("/")

    err = _require_publisher(namespace)
    if err:
        return err

    pending_path = _pending_meta_path(namespace, path)
    try:
        with open(pending_path, "r") as f:
            pending = json.loads(f.read())
    except FileNotFoundError:
        return json.dumps({"error": f"No pending upload for {namespace}/{path}"})

    total_chunks = pending["total_chunks"]
    content_type = pending.get("content_type") or _guess_content_type(path)

    for i in range(total_chunks):
        if not os.path.exists(_chunk_file_path(namespace, path, i)):
            return json.dumps({"error": f"Missing chunk {i} of {total_chunks}"})

    # Codex curation gate (issue #244) — a chunked manifest.json must not
    # bypass the kind: codex classification check in store_file.
    if path.split("/")[-1] == "manifest.json" or namespace.startswith(NS_PREFIX_CODEX):
        assembled = bytearray()
        for i in range(total_chunks):
            with open(_chunk_file_path(namespace, path, i), "rb") as cf:
                assembled.extend(cf.read())
        err = _codex_manifest_gate(namespace, path, bytes(assembled))
        if err:
            return err

    caller_str = ic.caller().to_str()
    _ensure_namespace_exists(namespace, caller_str)

    fp = _file_path(namespace, path)
    os.makedirs(os.path.dirname(fp), exist_ok=True)

    h = hashlib.sha256()
    total_size = 0
    with open(fp, "wb") as out:
        for i in range(total_chunks):
            chunk_path = _chunk_file_path(namespace, path, i)
            with open(chunk_path, "rb") as cf:
                chunk = cf.read()
            out.write(chunk)
            h.update(chunk)
            total_size += len(chunk)
            os.remove(chunk_path)

    os.remove(pending_path)
    sha256 = h.hexdigest()

    meta = _load_meta(namespace)
    meta.setdefault("files", {})[path] = {
        "size": total_size,
        "content_type": content_type,
        "sha256": sha256,
        "updated": ic.time(),
    }
    _save_meta(namespace, meta)

    return json.dumps({
        "ok": True,
        "namespace": namespace,
        "path": path,
        "size": total_size,
        "sha256": sha256,
    })


@update
def finalize_chunked_file_step(args: text) -> text:
    """Incremental variant of finalize_chunked_file.

    Each call concatenates up to ``batch_size`` chunks (default 1) into the
    output file and returns progress. Caller polls until ``done=true``.

    This avoids the per-message instruction budget (40B) being blown by
    multi-MB files, which the single-shot ``finalize_chunked_file`` does
    on the WASI Python runtime — observed on the 1.8 MB gz base WASM.

    The on-chain SHA-256 computation is *skipped*: hashing N MB of bytes
    with Python's hashlib costs ~30M instructions/MB, which dominates the
    finalize cost for any non-trivial file. Caller passes the SHA-256
    they computed locally (e.g. the same SHA the IC management canister
    expects for ``install_chunked_code``); the registry stores it as-is
    and serves it back via ``get_file`` / ``list_files``. Trust model is
    unchanged: the caller already authenticated via the namespace ACL.

    Args (JSON): {
        "namespace": str,
        "path": str,
        "expected_sha256": str (optional) — full-file sha256 hex; stored
            on commit. Cached after the first call so callers only need
            to send it once.
        "batch_size": int (optional, default 1) — chunks to process this
            call. Use 1 for multi-MB chunks, larger for many small chunks.
    }
    Returns JSON: {
        "ok": True,
        "done": bool,            # true once every chunk has been
                                 # concatenated and meta has been written
        "processed": int,        # chunks consumed so far
        "total": int,            # total chunks in the upload
        "size": int,             # only set when done=true
        "sha256": str,           # only set when done=true (may be "")
    }
    """
    try:
        params = json.loads(args)
    except (json.JSONDecodeError, ValueError) as e:
        return json.dumps({"error": f"invalid args (not JSON): {e}"})

    namespace = params["namespace"]
    path = params["path"].lstrip("/")
    batch_size = max(1, int(params.get("batch_size", 1)))
    expected_sha256 = params.get("expected_sha256", "") or ""

    err = _require_publisher(namespace)
    if err:
        return err

    pending_path = _pending_meta_path(namespace, path)
    try:
        with open(pending_path, "r") as f:
            pending = json.loads(f.read())
    except FileNotFoundError:
        return json.dumps({"error": f"No pending upload for {namespace}/{path}"})

    total_chunks = int(pending["total_chunks"])
    content_type = pending.get("content_type") or _guess_content_type(path)
    processed = int(pending.get("processed_chunks", 0))
    output_size = int(pending.get("output_size", 0))

    # Cache caller's expected sha on the first call so subsequent calls
    # don't have to repeat it.
    if expected_sha256 and not pending.get("expected_sha256"):
        pending["expected_sha256"] = expected_sha256
    if not expected_sha256:
        expected_sha256 = pending.get("expected_sha256", "")

    fp = _file_path(namespace, path)

    # First step: validate every chunk file exists, prep the output.
    if processed == 0:
        for i in range(total_chunks):
            if not os.path.exists(_chunk_file_path(namespace, path, i)):
                return json.dumps({"error": f"Missing chunk {i} of {total_chunks}"})
        # Codex curation gate (issue #244) — manifests are small, so
        # assembling the chunks for inspection here is cheap.
        if path.split("/")[-1] == "manifest.json" or namespace.startswith(NS_PREFIX_CODEX):
            assembled = bytearray()
            for i in range(total_chunks):
                with open(_chunk_file_path(namespace, path, i), "rb") as cf:
                    assembled.extend(cf.read())
            gate_err = _codex_manifest_gate(namespace, path, bytes(assembled))
            if gate_err:
                return gate_err
        caller_str = ic.caller().to_str()
        _ensure_namespace_exists(namespace, caller_str)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        # Truncate any prior partial output so retries are idempotent.
        open(fp, "wb").close()
        output_size = 0

    # Process this batch.
    end = min(processed + batch_size, total_chunks)
    with open(fp, "ab") as out:
        for i in range(processed, end):
            chunk_path = _chunk_file_path(namespace, path, i)
            with open(chunk_path, "rb") as cf:
                chunk = cf.read()
            out.write(chunk)
            output_size += len(chunk)
            os.remove(chunk_path)
    processed = end

    pending["processed_chunks"] = processed
    pending["output_size"] = output_size

    if processed < total_chunks:
        # Save resume state.
        with open(pending_path, "w") as f:
            f.write(json.dumps(pending))
        return json.dumps({
            "ok": True,
            "done": False,
            "processed": processed,
            "total": total_chunks,
        })

    # All chunks consumed — commit metadata and clean up.
    try:
        os.remove(pending_path)
    except OSError:
        pass

    meta = _load_meta(namespace)
    meta.setdefault("files", {})[path] = {
        "size": output_size,
        "content_type": content_type,
        "sha256": expected_sha256,
        "updated": ic.time(),
    }
    _save_meta(namespace, meta)

    return json.dumps({
        "ok": True,
        "done": True,
        "processed": processed,
        "total": total_chunks,
        "namespace": namespace,
        "path": path,
        "size": output_size,
        "sha256": expected_sha256,
    })


# ---------------------------------------------------------------------------
# HTTP endpoint — serve files with CORS headers
# GET /{namespace}/{path}  →  returns file content
# GET /                    →  returns namespaces JSON
# ---------------------------------------------------------------------------

def _http_response(status: int, body: bytes, content_type: str, extra_headers=None) -> dict:
    headers = [
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Methods", "GET, OPTIONS"),
        ("Access-Control-Allow-Headers", "Content-Type"),
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
    ]
    if extra_headers:
        headers.extend(extra_headers)
    return {
        "status_code": status,
        "headers": headers,
        "body": body,
        "streaming_strategy": None,
        "upgrade": None,
    }


def _handle_http(req: dict) -> dict:
    """Shared logic for http_request and http_request_update."""
    method = req["method"].upper()
    url = req["url"]
    path = url.split("?")[0].lstrip("/")

    if method == "OPTIONS":
        return _http_response(204, b"", "text/plain")

    # Root: return list of namespaces
    if not path:
        body = list_namespaces().encode("utf-8")
        return _http_response(200, body, "application/json")

    # API routes: /api/extensions, /api/codices
    if path == "api/extensions":
        body = list_extensions().encode("utf-8")
        return _http_response(200, body, "application/json")
    if path == "api/codices":
        body = list_codices().encode("utf-8")
        return _http_response(200, body, "application/json")

    # File serving: /{namespace-parts}/{file-path}
    # Need to find the namespace boundary. Try longest match first.
    # Namespaces can have slashes (e.g. "ext/voting/1.0.3")
    namespaces = _load_namespaces()
    matched_ns = None
    matched_file = None

    # Split path into segments and try progressively longer namespace prefixes
    segments = path.split("/")
    for i in range(len(segments), 0, -1):
        candidate_ns = "/".join(segments[:i])
        candidate_file = "/".join(segments[i:])
        if candidate_ns in namespaces:
            matched_ns = candidate_ns
            matched_file = candidate_file
            break

    if matched_ns is None:
        body = json.dumps({"error": f"No matching namespace for path: {path}"}).encode()
        return _http_response(404, body, "application/json")

    # If no file path, list files in namespace
    if not matched_file:
        body = list_files(json.dumps({"namespace": matched_ns})).encode("utf-8")
        return _http_response(200, body, "application/json")

    fp = _file_path(matched_ns, matched_file)
    try:
        with open(fp, "rb") as f:
            content = f.read()
    except FileNotFoundError:
        body = json.dumps({"error": f"Not found: {matched_ns}/{matched_file}"}).encode()
        return _http_response(404, body, "application/json")

    meta = _load_meta(matched_ns)
    file_info = meta.get("files", {}).get(matched_file, {})
    content_type = file_info.get("content_type") or _guess_content_type(matched_file)

    return _http_response(200, content, content_type, [
        ("Cache-Control", "public, max-age=3600"),
    ])


@query
def http_request(req: HttpRequest) -> HttpResponseIncoming:
    """Signal the gateway to upgrade to an update call for certified responses."""
    return {
        "status_code": 200,
        "headers": [],
        "body": b"",
        "streaming_strategy": None,
        "upgrade": True,
    }


@update
def http_request_update(req: HttpRequest) -> HttpResponseIncoming:
    """Serve files over HTTP with CORS. Runs as update so response is certified."""
    return _handle_http(req)
