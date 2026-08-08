"""Pure helpers for realm frontend ``.ic-assets.json5`` CSP patching."""

import re


def portal_url_to_origin(portal_url: str) -> str:
    """Extract scheme://host from a portal base or federation page URL."""
    url = (portal_url or "").strip().rstrip("/")
    if not url:
        return ""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    host = rest.split("/", 1)[0]
    return f"{scheme}://{host}"


def ensure_frame_ancestor(ic_assets_json5_text: str, origin: str) -> str:
    """Merge *origin* into the ``frame-ancestors`` CSP directive if missing.

    Returns the input unchanged when *origin* is empty, CSP is absent, or parsing
    fails (malformed input is never raised).
    """
    origin = (origin or "").strip().rstrip("/")
    if not origin:
        return ic_assets_json5_text or ""

    text = ic_assets_json5_text or ""
    try:
        match = re.search(
            r'("Content-Security-Policy"\s*:\s*")((?:\\.|[^"\\])*)(")',
            text,
            flags=re.DOTALL,
        )
        if not match:
            return text
        prefix, csp, suffix = match.group(1), match.group(2), match.group(3)
        new_csp = _merge_frame_ancestor(csp, origin)
        if new_csp == csp:
            return text
        return text[: match.start()] + prefix + new_csp + suffix + text[match.end() :]
    except Exception:
        return text


def _merge_frame_ancestor(csp: str, origin: str) -> str:
    parts = [p.strip() for p in csp.split(";") if p.strip()]
    fa_idx = None
    for i, part in enumerate(parts):
        if part.lower().startswith("frame-ancestors"):
            fa_idx = i
            break

    if fa_idx is None:
        parts.append(f"frame-ancestors {origin}")
        return ";".join(parts)

    fa = parts[fa_idx]
    tokens = fa.split(None, 1)
    if len(tokens) < 2:
        parts[fa_idx] = f"frame-ancestors {origin}"
        return ";".join(parts)

    directive_rest = tokens[1].strip()
    if directive_rest == "'none'":
        parts[fa_idx] = f"frame-ancestors {origin}"
        return ";".join(parts)

    if origin in directive_rest.split():
        return csp

    parts[fa_idx] = f"frame-ancestors {directive_rest} {origin}"
    return ";".join(parts)
