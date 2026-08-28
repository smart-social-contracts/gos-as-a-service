import json

from core.env_config import get_portal_url
from core.models import RealmRecord, SlugRecord, RegistryConfig
from _cdk import ic
from ic_python_logging import get_logger

logger = get_logger("slugs")

_SLUG_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-")

RESERVED_SLUGS = frozenset({
    "www", "api", "join", "deploy", "admin", "registry", "portal",
    "staging", "demo", "test", "static", "assets", "health", "faq",
    "create-realm", "deploy-gos", "my-dashboard", "connect", "r",
})

DEFAULT_LOADER_PROFILE = "realms-iframe-v1"
DEFAULT_GOS_IMPLEMENTATION = "realms-gos"
DEFAULT_GGG_CONFORMANCE = "1.0"

_PORTAL_HOSTS = {
    "staging": "https://staging.gos.earth",
    "demo": "https://demo.gos.earth",
    "test": "https://test.gos.earth",
    "ic": "https://registry.realmsgos.org",
    "production": "https://registry.realmsgos.org",
}


def normalize_slug(raw: str) -> str:
    s = (raw or "").strip().lower()
    out = []
    prev_hyphen = False
    for ch in s:
        if "a" <= ch <= "z" or "0" <= ch <= "9":
            out.append(ch)
            prev_hyphen = False
        elif not prev_hyphen and out:
            out.append("-")
            prev_hyphen = True
    s = "".join(out).strip("-")
    return s[:48]


def _slug_chars_valid(slug: str) -> bool:
    if not slug or len(slug) > 48:
        return False
    if slug[0] not in "abcdefghijklmnopqrstuvwxyz0123456789":
        return False
    if slug[-1] not in "abcdefghijklmnopqrstuvwxyz0123456789":
        return False
    for ch in slug:
        if ch not in _SLUG_CHARS:
            return False
    return True


def _validate_slug(slug: str):
    if not slug:
        return "Slug cannot be empty"
    if len(slug) > 48:
        return "Slug too long (max 48 characters)"
    if slug in RESERVED_SLUGS:
        return f"Slug '{slug}' is reserved"
    if not _slug_chars_valid(slug):
        return "Slug must be lowercase alphanumeric with hyphens"
    return None


def _portal_base_url(override: str = "") -> str:
    if override and override.strip():
        return override.strip().rstrip("/")
    configured = get_portal_url()
    if configured:
        return configured
    cfg = RegistryConfig["portal_base_url"]
    if cfg and cfg.value:
        return cfg.value.rstrip("/")
    net_cfg = RegistryConfig["portal_network"]
    network = (net_cfg.value if net_cfg else "staging").strip().lower()
    return _PORTAL_HOSTS.get(network, _PORTAL_HOSTS["staging"])


def _pretty_hostname(slug: str, portal_base: str, explicit: str = "") -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    host = portal_base.replace("https://", "").replace("http://", "")
    return f"{slug}.{host}"


def claim_slug_by_caller(
    slug: str,
    frontend_canister_id: str = "",
    realm_id: str = "",
    portal_base_url: str = "",
    pretty_hostname: str = "",
    gos_implementation: str = DEFAULT_GOS_IMPLEMENTATION,
    gos_version: str = "",
    ggg_conformance: str = DEFAULT_GGG_CONFORMANCE,
    loader_profile: str = DEFAULT_LOADER_PROFILE,
) -> dict:
    normalized = normalize_slug(slug)
    err = _validate_slug(normalized)
    if err:
        return {"success": False, "error": err}

    backend_id = (realm_id or str(ic.caller())).strip()
    frontend_id = (frontend_canister_id or "").strip()

    realm = RealmRecord[backend_id]
    if realm is None:
        return {"success": False, "error": f"Realm '{backend_id}' not registered"}

    if not frontend_id:
        frontend_id = (realm.frontend_canister_id or "").strip()
    if not frontend_id:
        return {"success": False, "error": "frontend_canister_id required"}

    existing = SlugRecord[normalized]
    if existing and existing.realm_id != backend_id:
        return {"success": False, "error": f"Slug '{normalized}' already claimed"}

    portal_base = _portal_base_url(portal_base_url)
    portal_url = f"{portal_base}/r/{normalized}"
    pretty = _pretty_hostname(normalized, portal_base, pretty_hostname)

    now = float(ic.time() / 1_000_000_000)
    caller = str(ic.caller())

    if existing:
        existing.realm_id = backend_id
        existing.frontend_canister_id = frontend_id
        existing.portal_url = portal_url
        existing.pretty_hostname = pretty
        existing.pretty_hostname_status = "pending"
        existing.gos_implementation = gos_implementation or DEFAULT_GOS_IMPLEMENTATION
        existing.gos_version = gos_version or ""
        existing.ggg_conformance = ggg_conformance or DEFAULT_GGG_CONFORMANCE
        existing.loader_profile = loader_profile or DEFAULT_LOADER_PROFILE
        existing.updated_at = now
    else:
        SlugRecord(
            slug=normalized,
            realm_id=backend_id,
            frontend_canister_id=frontend_id,
            claimed_by=caller,
            claimed_at=now,
            portal_url=portal_url,
            pretty_hostname=pretty,
            pretty_hostname_status="pending",
            gos_implementation=gos_implementation or DEFAULT_GOS_IMPLEMENTATION,
            gos_version=gos_version or "",
            ggg_conformance=ggg_conformance or DEFAULT_GGG_CONFORMANCE,
            loader_profile=loader_profile or DEFAULT_LOADER_PROFILE,
            created_at=now,
            updated_at=now,
        )

    realm.url = portal_url
    realm.frontend_canister_id = frontend_id

    return {
        "success": True,
        "slug": normalized,
        "portal_url": portal_url,
        "pretty_hostname": pretty,
        "pretty_hostname_status": "pending",
    }


def resolve_slug(slug: str) -> dict:
    normalized = normalize_slug(slug)
    record = SlugRecord[normalized]
    if record is None:
        return {"success": False, "error": f"Unknown slug '{normalized}'"}

    realm = RealmRecord[record.realm_id]
    backend_url = realm.backend_url if realm else ""

    return {
        "success": True,
        "slug": record.slug,
        "realm_id": record.realm_id,
        "backend_canister_id": record.realm_id,
        "frontend_canister_id": record.frontend_canister_id,
        "portal_url": record.portal_url or "",
        "backend_url": backend_url or "",
        "gos_implementation": record.gos_implementation or DEFAULT_GOS_IMPLEMENTATION,
        "gos_version": record.gos_version or "",
        "ggg_conformance": record.ggg_conformance or DEFAULT_GGG_CONFORMANCE,
        "loader_profile": record.loader_profile or DEFAULT_LOADER_PROFILE,
        "pretty_hostname": record.pretty_hostname or "",
        "pretty_hostname_status": record.pretty_hostname_status or "pending",
    }


def list_pending_pretty_hostnames() -> list:
    out = []
    for rec in SlugRecord.instances():
        if (rec.pretty_hostname_status or "") == "pending" and rec.pretty_hostname:
            out.append(rec.to_dict())
    out.sort(key=lambda r: r.get("claimed_at", 0))
    return out


def mark_pretty_hostname_status(slug: str, status: str) -> dict:
    normalized = normalize_slug(slug)
    allowed = {"pending", "live", "failed"}
    if status not in allowed:
        return {"success": False, "error": f"Invalid status '{status}'"}

    record = SlugRecord[normalized]
    if record is None:
        return {"success": False, "error": f"Unknown slug '{normalized}'"}

    record.pretty_hostname_status = status
    record.updated_at = float(ic.time() / 1_000_000_000)
    return {"success": True, "slug": normalized, "pretty_hostname_status": status}


def resolve_slug_json(slug: str) -> str:
    return json.dumps(resolve_slug(slug))
