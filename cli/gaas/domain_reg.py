"""IC custom domain registration via the HTTP gateway custom-domains API.

``https://icp0.io/custom-domains/v1/<domain>``:

- ``GET  /validate`` — DNS + ``/.well-known/ic-domains`` check, reports the canister
- ``GET``            — current registration (``registration_status``, ``canister_id``)
- ``POST``           — register a domain that has no registration yet
- ``PATCH``          — re-point an existing registration at the canister DNS now names

The old ``reg.icp0.io/domains`` service was retired in 2026 and now answers with
the gateway's "canister_id_not_resolved" page, so ``POST`` vs ``PATCH`` is chosen
from the current registration rather than guessed.
"""

from __future__ import annotations

import json
import time
from typing import Any

import requests

REG_API = "https://icp0.io/custom-domains/v1"

_DONE = {"registered", "active", "available", "ready", "completed"}
_FAILED = {"failed", "error", "rejected", "expired"}


class DomainRegistrationError(RuntimeError):
    pass


def _url(domain: str, suffix: str = "") -> str:
    return f"{REG_API}/{domain.rstrip('.').lower()}{suffix}"


def _payload(response: requests.Response, what: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = {"raw": response.text}
    if response.status_code >= 400 or (
        isinstance(payload, dict) and payload.get("status") not in (None, "success")
    ):
        raise DomainRegistrationError(
            f"{what} failed: HTTP {response.status_code} {json.dumps(payload)[:400]}"
        )
    return payload if isinstance(payload, dict) else {"raw": payload}


def _data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def registration_status(
    domain: str, *, session: requests.Session | None = None
) -> dict[str, Any] | None:
    """Current registration ``data`` or None when the domain is not registered."""
    http = session or requests.Session()
    response = http.get(_url(domain), timeout=60)
    if response.status_code == 404:
        return None
    return _data(_payload(response, f"GET {_url(domain)}"))


def validate_domain(domain: str, *, session: requests.Session | None = None) -> dict[str, Any]:
    http = session or requests.Session()
    response = http.get(_url(domain, "/validate"), timeout=60)
    return _data(_payload(response, f"GET {_url(domain, '/validate')}"))


def register_domain(domain: str, *, session: requests.Session | None = None) -> dict[str, Any]:
    """POST a fresh registration, or PATCH when the domain is already registered."""
    http = session or requests.Session()
    current = registration_status(domain, session=http)
    if current is None:
        response = http.post(_url(domain), timeout=60)
        return _data(_payload(response, f"POST {_url(domain)}"))
    response = http.patch(_url(domain), timeout=60)
    return _data(_payload(response, f"PATCH {_url(domain)}"))


def poll_domain_registration(
    domain: str,
    *,
    expected_canister: str | None = None,
    timeout: float = 600.0,
    poll_interval: float = 15.0,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Wait until the registration is ``registered`` (and, when given, points at
    ``expected_canister`` — a PATCH reports ``registered`` for the old canister
    until the gateways have switched)."""
    http = session or requests.Session()
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = registration_status(domain, session=http) or {}
        status = str(last.get("registration_status", last.get("status", ""))).lower()
        canister_ok = (
            expected_canister is None
            or str(last.get("canister_id", "")).lower() == expected_canister.lower()
        )
        if status in _DONE and canister_ok:
            return last
        if status in _FAILED:
            raise DomainRegistrationError(f"domain registration failed: {last}")
        time.sleep(poll_interval)
    raise DomainRegistrationError(f"domain registration timed out; last response: {last}")


def attempt_domain_registration(domain: str, *, timeout: float = 600.0) -> tuple[bool, str]:
    """Best-effort registration; returns (success, detail message)."""
    try:
        http = requests.Session()
        validation = validate_domain(domain, session=http)
        if str(validation.get("validation_status", "")).lower() not in ("valid", "ok", ""):
            return False, f"domain not eligible yet: {json.dumps(validation)}"
        wanted = str(validation.get("canister_id") or "") or None
        current = registration_status(domain, session=http)
        if (
            current
            and str(current.get("registration_status", "")).lower() in _DONE
            and wanted
            and str(current.get("canister_id", "")).lower() == wanted.lower()
        ):
            return True, json.dumps(current, indent=2)
        register_domain(domain, session=http)
        final = poll_domain_registration(
            domain, expected_canister=wanted, timeout=timeout, session=http
        )
        return True, json.dumps(final, indent=2)
    except DomainRegistrationError as exc:
        return False, str(exc)
    except requests.RequestException as exc:
        return False, f"registration API request failed: {exc}"
