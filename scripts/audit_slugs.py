#!/usr/bin/env python3
"""List the registry's slugs whose frontend canister the installer never deployed.

    REGISTRY_BACKEND=<id> REALM_INSTALLER=<id> python3 scripts/audit_slugs.py --network ic --identity <controller>

Read-only: both canisters are read through their `__browse__` query. It is
controller-only (basilisk's guard_against_non_controllers), so --identity is
required and must be a controller of both canisters. The portal iframes a slug's
`frontend_canister_id` and delegates the visitor's login to it, so every slug
must point at the realm and frontend a deployment job created (audit C1). Slugs
listed here need a look: a hijack, or an older realm whose job record is gone.
Exit status 1 when any slug is listed.

Environment: REGISTRY_BACKEND, REALM_INSTALLER, canister ids from `casals export`.
"""

import argparse
import json
import os
import subprocess
import sys

# The StableBTreeMap each canister's database lives in, named as in its main.py.
REGISTRY_MAP = "storage"
INSTALLER_MAP = "_db_storage"
PAGE_SIZE = 1000


def browse(canister: str, query: dict, network: str, identity: str | None) -> dict:
    """One `__browse__` query; returns the decoded JSON reply."""
    candid_text = json.dumps(query).replace("\\", "\\\\").replace('"', '\\"')
    cmd = ["icp", "canister", "call", canister, "__browse__", f'("{candid_text}")']
    cmd += ["--query", "--json", "-n", network]
    if identity:
        cmd += ["--identity", identity]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise SystemExit(f"__browse__ on {canister} failed: {result.stderr.strip()[-400:]}")
    reply = json.loads(result.stdout)
    while isinstance(reply, str):
        reply = json.loads(reply)
    if "error" in reply:
        raise SystemExit(f"__browse__ on {canister}: {reply['error']} {reply.get('available', '')}")
    return reply


def entities(canister: str, map_name: str, type_name: str, network: str, identity: str | None) -> list:
    """Every stored entity of *type_name*, as the dict the database saved."""
    prefix = f"{type_name}@"
    found = []
    offset = 0
    while True:
        page = browse(
            canister,
            {"action": "items", "map": map_name, "offset": offset, "limit": PAGE_SIZE},
            network,
            identity,
        )
        for key, value in page["result"]:
            if key.startswith(prefix):
                found.append(json.loads(value))
        offset += PAGE_SIZE
        if offset >= page["total"]:
            return found


def unverified_slugs(slugs: list, jobs: list) -> list:
    """The slugs whose realm and frontend no single deployment job recorded together."""
    deployed = {(job.get("backend_canister_id"), job.get("frontend_canister_id")) for job in jobs}
    return [s for s in slugs if (s.get("realm_id"), s.get("frontend_canister_id")) not in deployed]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--network", default="ic", help="icp network (default ic)")
    parser.add_argument("--identity", required=True, help="icp identity of a controller of both canisters")
    args = parser.parse_args()
    missing = [name for name in ("REGISTRY_BACKEND", "REALM_INSTALLER") if not os.environ.get(name)]
    if missing:
        sys.exit(f"set {', '.join(missing)} (ids from `casals export`)")

    slugs = entities(os.environ["REGISTRY_BACKEND"], REGISTRY_MAP, "SlugRecord", args.network, args.identity)
    jobs = entities(os.environ["REALM_INSTALLER"], INSTALLER_MAP, "DeploymentJob", args.network, args.identity)
    suspicious = unverified_slugs(slugs, jobs)

    print(f"{len(slugs)} slugs, {len(jobs)} deployment jobs, {len(suspicious)} slugs to check")
    for s in suspicious:
        print(f"  {s['slug']}: frontend {s['frontend_canister_id']} (realm {s['realm_id']}, claimed by {s['claimed_by']})")
    return 1 if suspicious else 0


if __name__ == "__main__":
    sys.exit(main())
