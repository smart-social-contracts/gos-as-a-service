"""Fail-closed liveness checks for IC canister principals.

Used before descriptor adopt and before a frontend bake that would inject a
portal URL. A missing principal (IC0301 / HTTP 404) must not be written or
baked. Known-dead IDs (fdr7z, installer ghosts, …) are rejected without a
network call.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

IC_API_CANISTER_URL = "https://ic-api.internetcomputer.org/api/v3/canisters/{canister_id}"
ICP0_FRONTEND_URL = "https://{canister_id}.icp0.io/"
_TIMEOUT_S = 20

# First group of principals that must never be baked into the portal.
# fdr7z = destroyed staging Casals UI; fksuf/hznxf/jj2e5/rbuam = installer/monitor ghosts.
KNOWN_DEAD_CANISTER_PREFIXES: frozenset[str] = frozenset(
    {
        "fdr7z",
        "jj2e5",
        "rbuam",
        "fksuf",
        "hznxf",
        "h6mrr",
    }
)

PORTAL_BAKED_NON_DNS_FRONTENDS: tuple[str, ...] = ("casals_frontend",)

LOCAL_NETWORKS: frozenset[str] = frozenset({"", "local", "localhost"})


class CanisterNotFoundError(RuntimeError):
    """The principal is missing on the IC (IC0301 / not found)."""


def canister_prefix(canister_id: str) -> str:
    return (canister_id or "").strip().split("-", 1)[0]


def is_known_dead_canister(canister_id: str) -> bool:
    return canister_prefix(canister_id) in KNOWN_DEAD_CANISTER_PREFIXES


def assert_not_known_dead(canister_id: str, *, role: str = "canister") -> None:
    principal = (canister_id or "").strip()
    if principal and is_known_dead_canister(principal):
        raise CanisterNotFoundError(
            f"refusing to use {role} {principal}: known-dead canister"
        )


def _is_not_found_payload(status: int, payload: object) -> bool:
    if status == 404:
        return True
    if not isinstance(payload, dict):
        text = str(payload).lower()
        return "ic0301" in text or "canister not found" in text or "canister_not_found" in text
    text = json.dumps(payload).lower()
    return (
        payload.get("status") == "Not Found"
        or payload.get("code") == 404
        or "ic0301" in text
        or "canister_not_found" in text
        or "canister not found" in text
    )


def _http_body_is_missing(status: int, body: str) -> bool:
    if status == 404:
        return True
    text = (body or "").lower()
    return (
        "ic0301" in text
        or "canister_not_found" in text
        or "canister not found" in text
        or "does not exist or is no longer available" in text
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


def fetch_frontend_http(
    canister_id: str,
    *,
    opener: urllib.request.OpenerDirector | None = None,
) -> tuple[int, str]:
    """GET the raw icp0.io frontend. Returns ``(http_status, body_prefix)``."""
    url = ICP0_FRONTEND_URL.format(canister_id=canister_id)
    request = urllib.request.Request(
        url,
        headers={"Accept": "text/html,application/json", "User-Agent": "gaas-canister-liveness/1.0"},
    )
    open_url = opener.open if opener is not None else urllib.request.urlopen
    try:
        with open_url(request, timeout=_TIMEOUT_S) as response:
            raw = response.read(2048).decode("utf-8", errors="replace")
            status = int(getattr(response, "status", 200) or 200)
            return status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read(2048).decode("utf-8", errors="replace") if exc.fp else ""
        return int(exc.code), raw


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


def assert_frontend_http_live(
    canister_id: str,
    *,
    role: str = "casals_frontend",
    http_get=None,
) -> None:
    """Fail if the icp0.io frontend 404s / IC0301 / canister not found."""
    principal = (canister_id or "").strip()
    if not principal:
        raise CanisterNotFoundError(f"refusing to use {role}: missing canister id")
    assert_not_known_dead(principal, role=role)

    lookup = http_get or fetch_frontend_http
    try:
        status, body = lookup(principal)
    except CanisterNotFoundError:
        raise
    except Exception as exc:
        raise CanisterNotFoundError(
            f"refusing to use {role} {principal}: frontend HTTP check failed ({exc})"
        ) from exc

    body_text = body if isinstance(body, str) else str(body)
    if _http_body_is_missing(int(status), body_text):
        raise CanisterNotFoundError(
            f"refusing to use {role} {principal}: canister not found (IC0301)"
        )


def fetch_local_canister_record(canister_id: str) -> tuple[int, object]:
    """Ask the local replica whether *canister_id* exists.

    Uses ``dfx canister status --network local``. Never calls
    ``ic-api.internetcomputer.org`` — local principals are not on mainnet.
    """
    from gaas.dfx import DfxError, canister_status, is_canister_not_found_error

    try:
        status = canister_status(canister_id, "local")
    except DfxError as exc:
        if is_canister_not_found_error(exc):
            return 404, {"error": "IC0301 canister not found"}
        return 500, {"error": str(exc)}
    return 200, {"canister_id": canister_id, "status": status.status}


def assert_installer_live_for_network(
    canister_id: str,
    network: str,
    *,
    fetch=None,
) -> None:
    """Fail closed before adopt or a frontend bake that would inject the installer ID.

    Empty ``canister_id`` is the create path (nothing to check). Persistent
    networks use the IC API. ``local`` / ``localhost`` ping the local replica
    so a ghost principal still fails closed without talking to mainnet.
    """
    net = (network or "").strip().lower()
    principal = (canister_id or "").strip()
    if not principal:
        return
    if net in ("local", "localhost"):
        assert_canister_exists(
            principal,
            role="realm_installer",
            fetch=fetch or fetch_local_canister_record,
        )
        return
    if net == "":
        return
    assert_canister_exists(principal, role="realm_installer", fetch=fetch)


def assert_casals_frontend_live(
    canister_id: str,
    network: str,
    *,
    fetch=None,
    http_get=None,
    require_http: bool = False,
) -> None:
    """Guard a baked Casals frontend. Unset is allowed; a dead ID is not."""
    net = (network or "").strip().lower()
    if net in LOCAL_NETWORKS:
        return
    principal = (canister_id or "").strip()
    if not principal:
        return
    assert_not_known_dead(principal, role="casals_frontend")
    if require_http:
        assert_frontend_http_live(principal, role="casals_frontend", http_get=http_get)
        return
    if fetch is not None or http_get is None:
        assert_canister_exists(principal, role="casals_frontend", fetch=fetch)
    if http_get is not None:
        assert_frontend_http_live(principal, role="casals_frontend", http_get=http_get)


def collect_baked_portal_frontends(repo_root: Path) -> list[tuple[str, str, str, str]]:
    """``(source, env, role, canister_id)`` for portal-baked non-DNS frontends."""
    root = Path(repo_root)
    found: list[tuple[str, str, str, str]] = []

    ids_path = root / "canister_ids.json"
    if ids_path.is_file():
        data = json.loads(ids_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for role in PORTAL_BAKED_NON_DNS_FRONTENDS:
                entry = data.get(role) or {}
                if not isinstance(entry, dict):
                    continue
                for env, cid in entry.items():
                    if cid:
                        found.append((str(ids_path), str(env), role, str(cid)))

    env_dir = root / "environments"
    if env_dir.is_dir():
        for env_file in sorted(env_dir.glob("*.json")):
            payload = json.loads(env_file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            canisters = payload.get("canisters") or {}
            if not isinstance(canisters, dict):
                continue
            env_name = str(payload.get("name") or env_file.stem)
            for role in PORTAL_BAKED_NON_DNS_FRONTENDS:
                cid = canisters.get(role)
                if cid:
                    found.append((str(env_file), env_name, role, str(cid)))
    return found


def probe_baked_portal_frontends(
    repo_root: Path,
    *,
    http_get=None,
) -> None:
    """Fail if any committed portal Casals frontend 404s / is known-dead."""
    seen: set[tuple[str, str]] = set()
    for _source, env, role, cid in collect_baked_portal_frontends(repo_root):
        key = (role, cid)
        if key in seen:
            continue
        seen.add(key)
        if (env or "").strip().lower() in LOCAL_NETWORKS:
            continue
        assert_casals_frontend_live(
            cid,
            env,
            http_get=http_get,
            require_http=True,
        )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(
            "usage: python3 -m gaas.canister_liveness <canister_id> [role]\n"
            "       python3 -m gaas.canister_liveness --probe-baked [repo_root]",
            file=sys.stderr,
        )
        return 2
    try:
        if args[0] == "--probe-baked":
            root = Path(args[1]) if len(args) > 1 else Path.cwd()
            probe_baked_portal_frontends(root)
            return 0
        role = args[1] if len(args) > 1 else "realm_installer"
        if role in PORTAL_BAKED_NON_DNS_FRONTENDS:
            assert_frontend_http_live(args[0], role=role)
        else:
            assert_canister_exists(args[0], role=role)
    except CanisterNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
