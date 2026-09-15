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
     backend answers `status`.

Usage:  CASALS_HOME=/tmp/e2e-gaas python tests/e2e/deploy_realm.py [realm-name]
Env:    ENV (default local), IDENTITY (default local-dev), TIMEOUT_S (default 1500)
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
GATEWAY = "http://127.0.0.1:8000"


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


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else f"e2e-realm-{int(time.time()) % 100000}"
    casals_id = conductor_backend()
    b = bindings(casals_id)
    registry, installer = b["realm-registry-backend"], b["realm-installer"]
    portal = f"http://{b['realm-registry-frontend']}.localhost:8000"
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
            "open_registration": False, "extensions": [],
        },
        "casals": {"section": "Deployments", "stand": name},
        "federation": {"slug": name, "portal_url": f"{portal}/r/{name}"},
    }
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

    url = f"http://{frontend}.localhost:8000"
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

    print(json.dumps({
        "ok": True, "realm": name, "job_id": job_id, "job_status": view.get("status"),
        "backend": backend, "frontend": frontend, "frontend_url": url,
        "portal_url": f"{portal}/r/{name}", "casals_members": sorted(k for k in live if k.startswith(name)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fail as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
