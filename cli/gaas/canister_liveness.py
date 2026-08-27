"""Fail-closed liveness checks for IC canister principals.

Used before descriptor adopt and before a staging frontend bake that would
inject ``CANISTER_ID_REALM_INSTALLER``. A missing principal (IC0301 / HTTP
404) must not be written or baked.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

IC_API_CANISTER_URL = "https://ic-api.internetcomputer.org/api/v3/canisters/{canister_id}"
_TIMEOUT_S = 20


class CanisterNotFoundError(RuntimeError):
    """The principal is missing on the IC (IC0301 / not found)."""


def _is_not_found_payload(status: int, payload: object) -> bool:
    if status == 404:
        return True
    if not isinstance(payload, dict):
        return False
    text = json.dumps(payload).lower()
    return (
        payload.get("status") == "Not Found"
        or payload.get("code") == 404
        or "ic0301" in text
        or "not found" in text
    )


def fetch_canister_record(
    canister_id: str,
    *,
    opener: urllib.request.OpenerDirector | None = None,
) -> tuple[int, object]:
    """Anonymous IC API lookup. Returns ``(http_status, json_or_text)``."""
    url = IC_API_CANISTER_URL.format(canister_id=canister_id)
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "gaas-canister-liveness/1.0"},
    )
    open_url = opener.open if opener is not None else urllib.request.urlopen
    try:
        with open_url(request, timeout=_TIMEOUT_S) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        status = int(exc.code)
    try:
        payload: object = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = raw
    return status, payload


def assert_canister_exists(
    canister_id: str,
    *,
    role: str = "canister",
    fetch=None,
) -> None:
    """Raise ``CanisterNotFoundError`` if *canister_id* is missing on the IC."""
    principal = (canister_id or "").strip()
    if not principal:
        raise CanisterNotFoundError(f"refusing to use {role}: missing canister id")

    lookup = fetch or fetch_canister_record
    try:
        status, payload = lookup(principal)
    except CanisterNotFoundError:
        raise
    except Exception as exc:
        raise CanisterNotFoundError(
            f"refusing to use {role} {principal}: liveness check failed ({exc})"
        ) from exc

    if _is_not_found_payload(status, payload):
        raise CanisterNotFoundError(
            f"refusing to use {role} {principal}: canister not found (IC0301)"
        )
    if status != 200:
        raise CanisterNotFoundError(
            f"refusing to use {role} {principal}: liveness check failed (HTTP {status})"
        )
    if isinstance(payload, dict) and not payload.get("canister_id"):
        raise CanisterNotFoundError(
            f"refusing to use {role} {principal}: canister not found (IC0301)"
        )


def assert_installer_live_for_network(
    canister_id: str,
    network: str,
    *,
    fetch=None,
) -> None:
    """Fail closed for persistent networks before adopt or a staging bake."""
    net = (network or "").strip().lower()
    if net in ("", "local", "localhost"):
        return
    assert_canister_exists(canister_id, role="realm_installer", fetch=fetch)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(
            "usage: python3 -m gaas.canister_liveness <canister_id> [role]",
            file=sys.stderr,
        )
        return 2
    role = args[1] if len(args) > 1 else "realm_installer"
    try:
        assert_canister_exists(args[0], role=role)
    except CanisterNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
