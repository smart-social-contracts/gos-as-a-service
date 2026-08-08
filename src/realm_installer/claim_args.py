"""Pure helpers for building Candid argument strings (no IC/basilisk imports)."""

_GOS_KEYS = ("implementation", "version", "ggg_conformance", "loader_profile")


def _escape_candid_text(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _candid_text(value: str) -> str:
    return f'"{_escape_candid_text(value)}"'


def _candid_opt_text(value: str | None) -> str:
    if value is None:
        return "null"
    return f'opt "{_escape_candid_text(value)}"'


def _portal_base_url(manifest: dict) -> str:
    """Portal base URL for claim_slug, derived from the wizard manifest.

    The frontend writes ``federation.portal_url = "<host>/r/<slug>"`` — strip
    the path so the registry records realms under the portal the wizard ran on
    instead of defaulting to staging.
    """
    fed = manifest.get("federation")
    if not isinstance(fed, dict):
        return ""
    url = str(fed.get("portal_url") or "").strip()
    if not url:
        return ""
    return url.split("/r/")[0].rstrip("/")


def build_claim_slug_args(
    slug: str,
    frontend_id: str,
    backend_id: str,
    manifest: dict,
) -> str:
    """Build the textual Candid tuple for registry ``claim_slug``.

    Legacy manifests without a ``gos`` block use the 5-arg form (trailing opts
    omitted; Candid subtyping accepts fewer arguments). When ``gos`` is present,
    emit all four trailing ``opt text`` fields; missing keys become ``null``.
    The 4th positional arg carries the portal base URL from the manifest.
    """
    portal_base = _portal_base_url(manifest)
    base = (
        f"({_candid_text(slug)}, {_candid_text(frontend_id)}, "
        f'{_candid_text(backend_id)}, {_candid_text(portal_base)}, "")'
    )
    gos = manifest.get("gos")
    if not gos:
        return base

    if not isinstance(gos, dict):
        gos = {}

    opts = ", ".join(_candid_opt_text(gos.get(key)) for key in _GOS_KEYS)
    return (
        f"({_candid_text(slug)}, {_candid_text(frontend_id)}, "
        f'{_candid_text(backend_id)}, {_candid_text(portal_base)}, "", {opts})'
    )
