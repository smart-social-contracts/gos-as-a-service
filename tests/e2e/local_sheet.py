#!/usr/bin/env python3
"""The GaaS sheet with local builds in place of the releases it pins, for an e2e of unreleased code.

`casals.json` installs release artifacts everywhere, the local environment included. This writes a copy
whose registry rows point at files you built, and whose `Deployments` template installs them: the realm
backend (backend and quarter rows), the realm frontend, the installer and the Casals conductor. Anything
not given keeps its release.

Usage:  python tests/e2e/local_sheet.py [out.json]      (default casals.local-build.json beside casals.json)
Env:    REALM_VERSION        the version label of the realm builds (default local); a new label for each
                             build lets `casals upgrade` upload it beside the last one
        REALM_BACKEND_WASM   realm backend .wasm or .wasm.gz
        REALM_FRONTEND       realm frontend dist directory or bundle .tgz
        INSTALLER_WASM       realm installer .wasm or .wasm.gz
        CASALS_BACKEND_WASM  Casals conductor .wasm or .wasm.gz
Absolute paths outside this checkout need their directory in CASALS_LOCAL_ROOTS when `casals up` reads them.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHEET = os.path.join(HERE, "..", "..", "casals.json")


def local_source(path: str) -> str:
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise SystemExit(f"{path}: no such file")
    return f"local:{path}"


def wasm_row(sheet: dict, family: str) -> dict:
    return next(w for w in sheet["registry"]["wasms"] if w["family"] == family)


def build_sheet(sheet: dict, env: dict) -> dict:
    version = env.get("REALM_VERSION") or "local"
    template = next(s for s in sheet["sections"] if s["name"] == "Deployments")["arrangements"]["stand_template"]
    rows = {c["name"]: c for c in template["canisters"]}
    if env.get("REALM_BACKEND_WASM"):
        row = wasm_row(sheet, "realm-backend")
        row.update(version=version, source=local_source(env["REALM_BACKEND_WASM"]))
        row.pop("sha256", None)
        for name in ("{stand}-backend", "{stand}-quarter-{n}"):
            rows[name]["wasm"] = f"realm-backend@{version}"
    if env.get("REALM_FRONTEND"):
        path = f"release/realm/{version}/frontend"
        bundle = next(b for b in sheet["registry"]["bundles"] if b["path"].startswith("release/realm/"))
        bundle.update(path=path, source=local_source(env["REALM_FRONTEND"]))
        bundle.pop("sha256", None)
        rows["{stand}-frontend"]["content"] = path
    for family, var in (("realm-installer", "INSTALLER_WASM"), ("casals-backend", "CASALS_BACKEND_WASM")):
        if env.get(var):
            row = wasm_row(sheet, family)
            row["source"] = local_source(env[var])
            row.pop("sha256", None)
    return sheet


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(SHEET), "casals.local-build.json")
    sheet = build_sheet(json.load(open(SHEET)), dict(os.environ))
    with open(out, "w") as f:
        json.dump(sheet, f, indent=2)
        f.write("\n")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
