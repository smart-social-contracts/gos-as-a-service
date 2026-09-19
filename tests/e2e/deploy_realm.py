#!/usr/bin/env python3
"""Product e2e: a realm is born the way the portal does it.

Against a GaaS orchestra that `casals up` already converged on the local
replica (`CASALS_HOME=/tmp/e2e-gaas python tests/e2e/run_e2e.py ../gos-as-a-service/casals.json`
in the Casals repo, with KEEP=1), this script

  1. calls `realm-registry-backend.request_deployment(manifest)` as the operator,
     exactly what the portal wizard sends;
  2. polls the installer's job until it leaves the provisioning/bootstrap states —
     the installer only calls Casals `create_stand` and waits for the conductor's
     reconcile timer to build the stand from the `Deployments` template;
  3. checks the realm frontend serves `/canister_ids.js` pointing at the realm
     backend (written by Casals from the template's `files`), and that the
     backend answers `status`;
  4. with REALM_CODEX / REALM_EXTENSIONS set, asks for that content the way the
     wizard does (`realm.codex.package`, `realm.extensions`) and checks the
     installer fetched it from the file registry into the realm — the content
     path production depends on (`realms files publish` must have run first).

Usage:  CASALS_HOME=/tmp/e2e-gaas python tests/e2e/deploy_realm.py [realm-name]
Env:    ENV (default local), IDENTITY (default local-dev), TIMEOUT_S (default 1500),
        REALM_CODEX (codex id[@version]), REALM_EXTENSIONS (comma-separated ids)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

ENV = os.environ.get("ENV", "local")
IDENTITY = os.environ.get("IDENTITY", "local-dev")
HOME = os.environ.get("CASALS_HOME") or os.path.expanduser("~/.casals")
TIMEOUT_S = int(os.environ.get("TIMEOUT_S", "1500"))
REALM_CODEX = (os.environ.get("REALM_CODEX") or "").strip()
REALM_EXTENSIONS = [e.strip() for e in (os.environ.get("REALM_EXTENSIONS") or "").split(",") if e.strip()]
def _gateway_port() -> str:
    explicit = (os.environ.get("CASALS_REPLICA_PORT") or "").strip()
    if explicit.isdigit():
        return explicit
    url = (os.environ.get("CASALS_NETWORK_URL") or "").strip()
    if url.rsplit(":", 1)[-1].isdigit():
        return url.rsplit(":", 1)[-1]
    return "8000"


GATEWAY = os.environ.get("CASALS_NETWORK_URL", "http://127.0.0.1:8000").rstrip("/")
GATEWAY_PORT = _gateway_port()


class Fail(Exception):
    pass


def candid_text(s: str) -> str:
    return '("' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '")'


def icp(*args: str, timeout: int = 300) -> str:
    cmd = ["icp", *args, "-e", ENV, "--identity", IDENTITY, "--project-root-override", PROJECT_DIR]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        raise Fail(f"{' '.join(cmd[:5])} failed:\n{res.stderr[-1500:]}")
    return res.stdout


def unquote_candid_text(out: str) -> str:
    """`("{\"ok\": true}")` → `{"ok": true}`."""
    s = out.strip()
    s = s[1:-1].strip().rstrip(",") if s.startswith("(") and s.endswith(")") else s
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return s.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")


def call_json(cid: str, method: str, arg: str | None = None, *, query: bool = False) -> dict:
    args = ["canister", "call", cid, method, candid_text(arg) if arg is not None else "()"]
    if query:
        args.append("--query")
    text = unquote_candid_text(icp(*args))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise Fail(f"{method}: not JSON: {text[:300]}")


def _bindings_file() -> dict:
    # `casals up` writes <home>/gaas.<env>.json; the Casals e2e harness gives
    # every orchestra its own sub-home, <CASALS_HOME>/gaas/. Accept both so the
    # same CASALS_HOME works for the harness and for this script.
    candidates = [os.path.join(HOME, f"gaas.{ENV}.json"), os.path.join(HOME, "gaas", f"gaas.{ENV}.json")]
    for path in candidates:
        if os.path.isfile(path):
            with open(path) as fh:
                return json.load(fh)
    raise Fail(f"no gaas bindings under CASALS_HOME={HOME} (looked for {', '.join(candidates)}); run casals up first")


# icp-cli wants a project: reuse the one `casals up` keeps for this orchestra.
PROJECT_DIR = _bindings_file()["icp_project_dir"]


def conductor_backend() -> str:
    return _bindings_file()["backend_id"]


def bindings(casals_id: str) -> dict:
    res = call_json(casals_id, "get_bindings", query=True)
    return res.get("bindings") or {}


def job_status(installer: str, job_id: str) -> dict:
    """`get_deployment_job_status` returns a Candid variant record; read the
    fields we need with a tolerant scan instead of a Candid parser."""
    # Without the .did, icp prints field hashes instead of names.
    did = os.path.join(os.path.dirname(__file__), "..", "..", "src", "realm_installer", "realm_installer.did")
    out = icp("canister", "call", installer, "get_deployment_job_status", candid_text(job_id), "--query",
              "--candid", os.path.abspath(did))
    view = {}
    for key in ("status", "backend_canister_id", "frontend_canister_id", "error"):
        marker = f"{key} = \""
        if marker in out:
            start = out.index(marker) + len(marker)
            view[key] = out[start:out.index('"', start)]
    return view


def fetch(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def _ids(payload) -> set[str]:
    """Installed ids out of `list_runtime_extensions` ({"runtime_extensions": [...]})
    or `list_codex_packages` ({"codex_packages": [...]})."""
    if isinstance(payload, dict):
        for key in ("runtime_extensions", "codex_packages"):
            if isinstance(payload.get(key), list):
                return {str(x) for x in payload[key]}
        if payload.get("error"):
            raise Fail(f"realm listing failed: {payload['error']}")
    return set()


def check_content(backend: str) -> dict:
    """With REALM_CODEX / REALM_EXTENSIONS: wait until the realm reports them installed."""
    want_codex = REALM_CODEX.partition("@")[0]
    if not want_codex and not REALM_EXTENSIONS:
        return {}
    deadline = time.time() + 600
    seen_ext: set[str] = set()
    seen_cdx: set[str] = set()
    while time.time() < deadline:
        seen_ext = _ids(call_json(backend, "list_runtime_extensions", query=True))
        seen_cdx = _ids(call_json(backend, "list_codex_packages", query=True)) if want_codex else set()
        if set(REALM_EXTENSIONS) <= seen_ext and (not want_codex or want_codex in seen_cdx):
            return {"extensions": sorted(seen_ext), "codices": sorted(seen_cdx)}
        time.sleep(15)
    raise Fail(
        f"content missing after install: extensions want {REALM_EXTENSIONS} have {sorted(seen_ext)}; "
        f"codex want {want_codex or '-'} have {sorted(seen_cdx)}"
    )


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else f"e2e-realm-{int(time.time()) % 100000}"
    casals_id = conductor_backend()
    b = bindings(casals_id)
    registry, installer = b["realm-registry-backend"], b["realm-installer"]
    portal = f"http://{b['realm-registry-frontend']}.localhost:{GATEWAY_PORT}"
    print(f"conductor {casals_id}  registry {registry}  installer {installer}")

    manifest = {
        "name": name,
        "network": ENV,
        "deploy_mode": "install",
        "deploy_scope": "both",
        "deploy_version": "main",
        "gos": {"implementation": "realms-gos", "version": "main"},
        "realm": {
            "name": name, "display_name": name,
            "manifesto": f"Welcome to {name}.", "welcome_message": f"Welcome to {name}!",
            "open_registration": False, "extensions": list(REALM_EXTENSIONS),
        },
        "casals": {"section": "Deployments", "stand": name},
        "federation": {"slug": name, "portal_url": f"{portal}/r/{name}"},
    }
    if REALM_CODEX:
        codex_id, _, codex_version = REALM_CODEX.partition("@")
        manifest["realm"]["codex"] = {"package": codex_id, **({"version": codex_version} if codex_version else {})}
    res = call_json(registry, "request_deployment", json.dumps(manifest))
    if not res.get("success"):
        raise Fail(f"request_deployment: {res}")
    job_id = res["job_id"]
    print(f"job {job_id} enqueued for realm {name!r}")

    deadline = time.time() + TIMEOUT_S
    last = None
    while time.time() < deadline:
        view = job_status(installer, job_id)
        if view != last:
            print(f"  {time.strftime('%H:%M:%S')} job {view.get('status')} "
                  f"backend={view.get('backend_canister_id') or '-'} frontend={view.get('frontend_canister_id') or '-'}"
                  + (f" error={view['error']}" if view.get("error") else ""))
            last = view
        if view.get("status") in ("completed", "registering"):
            break
        if view.get("status", "").startswith("failed") or view.get("status") == "cancelled":
            raise Fail(f"job ended in {view.get('status')}: {view.get('error')}")
        time.sleep(15)
    else:
        raise Fail(f"job still {last and last.get('status')} after {TIMEOUT_S}s")

    backend, frontend = view["backend_canister_id"], view["frontend_canister_id"]
    live = bindings(casals_id)
    for member in (f"{name}-backend", f"{name}-frontend", f"{name}-baton"):
        if member not in live:
            raise Fail(f"Casals has no binding for {member}: {sorted(k for k in live if k.startswith(name))}")
    if live[f"{name}-backend"] != backend or live[f"{name}-frontend"] != frontend:
        raise Fail("installer and Casals disagree on the realm's canister ids")

    url = f"http://{frontend}.localhost:{GATEWAY_PORT}"
    # The conductor syncs the dist on its timer, a slice per tick: wait for the
    # generated config and the app shell.
    for _ in range(60):
        code, js = fetch(f"{url}/canister_ids.js")
        html_code, _ = fetch(f"{url}/index.html")
        if code == 200 and backend in js and html_code == 200:
            break
        time.sleep(15)
    else:
        raise Fail(f"{url}: canister_ids.js HTTP {code} (names backend: {backend in js}), index.html HTTP {html_code}")
    icp("canister", "call", backend, "status", "()", "--query")  # the realm backend answers

    installed = check_content(backend)

    print(json.dumps({
        "ok": True, "realm": name, "job_id": job_id, "job_status": view.get("status"),
        "backend": backend, "frontend": frontend, "frontend_url": url,
        "portal_url": f"{portal}/r/{name}", "casals_members": sorted(k for k in live if k.startswith(name)),
        **installed,
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fail as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
