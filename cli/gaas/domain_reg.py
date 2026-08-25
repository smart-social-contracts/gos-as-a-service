"""IC custom domain registration via reg.icp0.io."""

from __future__ import annotations

import json
import time
from typing import Any

import requests

REG_API = "https://reg.icp0.io/domains"


def custom_domain_already_live(domain: str, *, timeout: float = 20.0) -> bool:
    """True when HTTPS already serves ``/.well-known/ic-domains`` for this host."""
    host = domain.rstrip(".").lower()
    if not host:
        return False
    url = f"https://{host}/.well-known/ic-domains"
    try:
        response = requests.get(url, timeout=timeout)
    except requests.RequestException:
        return False
    if response.status_code != 200:
        return False
    return host in (response.text or "").lower()


class DomainRegistrationError(RuntimeError):
    pass


def register_domain(domain: str, *, session: requests.Session | None = None) -> dict[str, Any]:
    http = session or requests.Session()
    response = http.post(REG_API, json={"domain": domain.rstrip(".").lower()}, timeout=60)
    if response.status_code >= 400:
        raise DomainRegistrationError(
            f"POST {REG_API} failed: HTTP {response.status_code} {response.text}"
        )
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = {"raw": response.text}
    if not isinstance(payload, dict):
        return {"raw": payload}
    return payload


def poll_domain_registration(
    domain_id: str,
    *,
    timeout: float = 600.0,
    poll_interval: float = 15.0,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    http = session or requests.Session()
    url = f"{REG_API}/{domain_id}"
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = http.get(url, timeout=60)
        if response.status_code >= 400:
            raise DomainRegistrationError(
                f"GET {url} failed: HTTP {response.status_code} {response.text}"
            )
        try:
            last = response.json()
        except json.JSONDecodeError:
            last = {"raw": response.text}
        status = str(last.get("status", last.get("state", ""))).lower()
        if status in {"active", "available", "registered", "ready", "completed"}:
            return last
        if status in {"failed", "error", "rejected"}:
            raise DomainRegistrationError(f"domain registration failed: {last}")
        time.sleep(poll_interval)
    raise DomainRegistrationError(f"domain registration timed out; last response: {last}")


def attempt_domain_registration(domain: str, *, timeout: float = 600.0) -> tuple[bool, str]:
    """Best-effort registration; returns (success, detail message)."""
    if custom_domain_already_live(domain):
        return True, "custom domain already serving; skipped IC registration API"
    try:
        created = register_domain(domain)
        domain_id = (
            created.get("id")
            or created.get("domain_id")
            or created.get("registration_id")
            or domain
        )
        final = poll_domain_registration(str(domain_id), timeout=timeout)
        return True, json.dumps(final, indent=2)
    except DomainRegistrationError as exc:
        if custom_domain_already_live(domain):
            return True, f"custom domain already serving; registration API: {exc}"
        return False, str(exc)
    except requests.RequestException as exc:
        if custom_domain_already_live(domain):
            return True, f"custom domain already serving; registration API: {exc}"
        return False, f"registration API request failed: {exc}"
