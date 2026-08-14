"""Merge helpers for Casals frontend ``.ic-assets.json5``.

gaas must not overwrite the Casals asset policy. It only adds the ``ic_env``
cookie and, when configured, the off-chain monitor origin to ``connect-src``.
See https://github.com/smart-social-contracts/gos-as-a-service/issues/19
"""

from __future__ import annotations

import json


def url_to_origin(url: str) -> str:
    """Extract ``scheme://host`` from a service URL (path is dropped)."""
    value = (url or "").strip().rstrip("/")
    if not value:
        return ""
    if "://" not in value:
        return value
    scheme, rest = value.split("://", 1)
    host = rest.split("/", 1)[0]
    return f"{scheme}://{host}"


def merge_connect_src(csp: str, origin: str) -> str:
    """Add *origin* to the ``connect-src`` directive if missing."""
    origin = (origin or "").strip().rstrip("/")
    if not origin:
        return csp
    parts = [p.strip() for p in csp.split(";") if p.strip()]
    idx = None
    for i, part in enumerate(parts):
        if part.lower().startswith("connect-src"):
            idx = i
            break
    if idx is None:
        parts.append(f"connect-src {origin}")
    else:
        tokens = parts[idx].split()
        if origin in tokens[1:]:
            return csp
        parts[idx] = f"{parts[idx]} {origin}"
    joined = "; ".join(parts)
    if csp.strip().endswith(";"):
        return joined + ";"
    return joined


def merge_casals_ic_assets(
    existing_text: str,
    cookie_header: str,
    monitor_origin: str = "",
) -> str:
    """Preserve existing asset rules; add Set-Cookie and optional connect-src."""
    text = existing_text if (existing_text or "").strip() else "[]"
    try:
        config = json.loads(text)
    except json.JSONDecodeError:
        if monitor_origin:
            text = _patch_connect_src_in_text(text, monitor_origin)
        return text

    if isinstance(config, dict):
        config = [config]
    if not isinstance(config, list):
        config = []

    origin = url_to_origin(monitor_origin) if monitor_origin else ""
    if origin:
        for rule in config:
            if not isinstance(rule, dict):
                continue
            headers = rule.get("headers")
            if not isinstance(headers, dict):
                continue
            csp = headers.get("Content-Security-Policy")
            if isinstance(csp, str) and csp:
                headers["Content-Security-Policy"] = merge_connect_src(csp, origin)

    _upsert_html_cookie(config, cookie_header)
    return json.dumps(config, indent=2) + "\n"


def _upsert_html_cookie(config: list, cookie_header: str) -> None:
    html_match = "**/*.{html,shtml}"
    for rule in config:
        if not isinstance(rule, dict):
            continue
        if rule.get("match") == html_match:
            headers = rule.setdefault("headers", {})
            if not isinstance(headers, dict):
                rule["headers"] = {"Set-Cookie": cookie_header}
            else:
                headers["Set-Cookie"] = cookie_header
            return
    config.append(
        {
            "match": html_match,
            "headers": {"Set-Cookie": cookie_header},
        }
    )


def _patch_connect_src_in_text(text: str, origin: str) -> str:
    """Best-effort string patch when the file is not strict JSON."""
    origin = url_to_origin(origin)
    if not origin:
        return text
    marker = '"Content-Security-Policy"'
    start = text.find(marker)
    if start < 0:
        return text
    colon = text.find(":", start + len(marker))
    quote = text.find('"', colon + 1)
    if quote < 0:
        return text
    end = quote + 1
    while True:
        close = text.find('"', end)
        if close < 0:
            return text
        if text[close - 1] != "\\":
            csp = text[quote + 1 : close]
            patched = merge_connect_src(csp, origin)
            return text[: quote + 1] + patched + text[close:]
        end = close + 1
