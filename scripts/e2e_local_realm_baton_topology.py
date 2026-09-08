#!/usr/bin/env python3
"""Provision one realm on a local replica and assert Casals/baton end state.

Called from ``.github/workflows/gaas-e2e.yml`` after ``gaas new`` has seeded the
conductor and published Realms-GOS ``main`` artifacts into ``casals_file_registry``
(see ``phase_seed_file_registry`` — clones ``smart-social-contracts/realms`` at
``main`` and uploads ``realm-backend@main`` / ``realm-assets@main``). No extra
artifact publishing is done here; the assertions target orchestra topology and
baton wiring, not realm application behaviour.

Installer Casals/baton flags (``provision_via_casals``, ``create_stand_baton``,
``baton_wasm_key``) are already applied by ``gaas new`` via ``_installer_config_json``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from typing import Any

_DFX_ENV = {
    "TERM": os.environ.get("TERM", "xterm"),
    "DFX_WARNING": "-mainnet_plaintext_identity",
}


class E2EError(RuntimeError):
    """Assertion or driver failure with optional diagnostic attachments."""


def _log(msg: str) -> None:
    print(msg, flush=True)


def _candid_text_arg(payload: str) -> str:
    escaped = payload.replace("\\", "\\\\").replace('"', '\\"')
    return f'("{escaped}")'


def _run_dfx(
    args: list[str],
    *,
    network: str,
    identity: str | None = None,
    query: bool = False,
    timeout: int = 300,
) -> str:
    cmd = ["dfx", "canister", "call"]
    if identity:
        cmd.extend(["--identity", identity])
    cmd.extend(["--network", network])
    if query:
        cmd.append("--query")
    cmd.extend(args)
    env = {**os.environ, **_DFX_ENV}
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        raise E2EError(
            f"dfx call failed: {' '.join(cmd)}\n"
            f"stdout: {exc.stdout}\nstderr: {exc.stderr}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise E2EError(
            f"dfx call timed out after {timeout}s: {' '.join(cmd)}"
        ) from exc
    return result.stdout.strip()


_CANDID_ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "r": "\r", "t": "\t"}


def _unescape_candid(text: str) -> str:
    """Decode a candid text literal one escape at a time.

    Replacing \\" wholesale corrupts any value that itself contains escaped
    JSON - a section's stand_template, for instance - because the backslash of
    a \\\\ pair gets eaten and the quote after it is read as an escape.
    """
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch != "\\" or i + 1 >= len(text):
            out.append(ch)
            i += 1
            continue
        escaped = _CANDID_ESCAPES.get(text[i + 1])
        if escaped is None:
            out.append(ch)
            i += 1
        else:
            out.append(escaped)
            i += 2
    return "".join(out)


def _parse_candid_text(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1].strip()
    if raw.endswith(","):
        raw = raw[:-1].strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    return _unescape_candid(raw)


def _dfx_json(
    canister_id: str,
    method: str,
    arg: str,
    network: str,
    *,
    identity: str | None = None,
    query: bool = False,
    timeout: int = 300,
) -> Any:
    cmd = ["dfx", "canister", "call"]
    if identity:
        cmd.extend(["--identity", identity])
    cmd.extend(["--network", network, "--output", "json"])
    if query:
        cmd.append("--query")
    cmd.extend([canister_id, method, arg])
    env = {**os.environ, **_DFX_ENV}
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        raise E2EError(
            f"dfx json call failed: {' '.join(cmd)}\n"
            f"stdout: {exc.stdout}\nstderr: {exc.stderr}"
        ) from exc
    return json.loads(result.stdout)


def _unwrap_ok(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        if payload.get("Err") is not None:
            err = payload["Err"]
            if isinstance(err, dict):
                message = err.get("message") or str(err)
            else:
                message = str(err)
            raise E2EError(f"canister returned Err: {message}")
        if "Ok" in payload:
            inner = payload["Ok"]
            if isinstance(inner, str):
                try:
                    return json.loads(inner)
                except json.JSONDecodeError:
                    return {"value": inner}
            if isinstance(inner, dict):
                return inner
            return {"value": inner}
        return payload
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {"value": payload}
    raise E2EError(f"unexpected response shape: {payload!r}")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "realm").lower()).strip("-")
    return (slug[:48] or "realm")


def load_descriptor(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    canisters = data.get("canisters") or {}
    required = (
        "realm_registry_backend",
        "realm_installer",
        "casals_backend",
        "casals_file_registry",
    )
    missing = [key for key in required if not (canisters.get(key) or "").strip()]
    if missing:
        raise E2EError(
            f"descriptor {path} missing canister ids after gaas new: {', '.join(missing)}"
        )
    return data


def build_manifest(
    descriptor: dict[str, Any],
    *,
    realm_name: str,
    network: str,
) -> dict[str, Any]:
    slug = slugify(realm_name)
    gos_entry = (descriptor.get("gos") or [{}])[0]
    deploy_version = "main"
    version_key = deploy_version
    backend_key = (
        (gos_entry.get("artifacts") or {}).get("backend_wasm_key") or "realm-backend"
    )
    frontend_key = (
        (gos_entry.get("artifacts") or {}).get("frontend_wasm_key") or "realm-assets"
    )
    casals_file_registry = (descriptor.get("canisters") or {}).get(
        "casals_file_registry", ""
    )
    domain = (descriptor.get("domain") or "local.localhost").strip()
    portal_base = f"https://{domain}".rstrip("/")

    manifest: dict[str, Any] = {
        "name": realm_name,
        "network": network,
        "deploy_mode": "install",
        "deploy_scope": "both",
        "deploy_version": version_key,
        "can_test_mode": bool((descriptor.get("flags") or {}).get("can_test_mode", True)),
        "gos": {
            "implementation": gos_entry.get("implementation") or "realms-gos",
            "version": deploy_version,
            "ggg_conformance": "1.0",
            "loader_profile": gos_entry.get("loader_profile") or "realms-iframe-v1",
        },
        "realm": {
            "name": realm_name,
            "display_name": realm_name,
            "manifesto": f"GaaS E2E realm {realm_name}.",
            "welcome_message": f"Welcome to {realm_name}.",
            "open_registration": False,
            "extensions": [],
        },
        "casals": {
            "section": "Deployments",
            "stand": slug,
            "backend_wasm_key": f"{backend_key}@{version_key}",
            "frontend_wasm_key": f"{frontend_key}@{version_key}",
        },
        "infra": {
            "file_registry_canister_id": casals_file_registry,
        },
        "federation": {
            "slug": slug,
            "portal_url": f"{portal_base}/r/{slug}",
        },
    }
    test_flags = descriptor.get("test_flags") or {}
    if test_flags:
        manifest["test_flags"] = dict(test_flags)
    elif manifest["can_test_mode"]:
        manifest["test_flags"] = {
            "test_mode": True,
            "ii_bypass": True,
            "user_self_registration": True,
        }
    return manifest


def request_deployment(
    registry_id: str,
    manifest: dict[str, Any],
    network: str,
    *,
    identity: str | None = None,
) -> str:
    manifest_json = json.dumps(manifest, separators=(",", ":"))
    raw = _run_dfx(
        [registry_id, "request_deployment", _candid_text_arg(manifest_json)],
        network=network,
        identity=identity,
        timeout=600,
    )
    text = _parse_candid_text(raw)
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise E2EError(f"request_deployment returned non-JSON: {text[:500]}") from exc
    if not result.get("success"):
        raise E2EError(
            f"request_deployment failed: {result.get('error') or result}"
        )
    job_id = (result.get("job_id") or "").strip()
    if not job_id:
        raise E2EError(f"request_deployment missing job_id: {result}")
    _log(f"  enqueued deployment job_id={job_id} realm={manifest.get('name')}")
    return job_id


def fetch_job_status(
    installer_id: str,
    job_id: str,
    network: str,
    *,
    identity: str | None = None,
) -> dict[str, Any]:
    payload = _dfx_json(
        installer_id,
        "get_deployment_job_status",
        _candid_text_arg(job_id),
        network,
        identity=identity,
        query=True,
    )
    return _unwrap_ok(payload)


def fetch_casals_tree(
    casals_id: str,
    network: str,
    *,
    identity: str | None = None,
) -> dict[str, Any]:
    raw = _run_dfx(
        [casals_id, "get_tree", "()"],
        network=network,
        identity=identity,
        query=True,
    )
    text = _parse_candid_text(raw)
    return json.loads(text)


def _find_stand(tree: dict[str, Any], section: str, stand: str) -> dict[str, Any] | None:
    for sec in tree.get("sections") or []:
        if (sec.get("name") or "").strip() != section:
            continue
        for item in sec.get("stands") or []:
            if (item.get("name") or "").strip() == stand:
                return item
    return None


def _canister_map(stand: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for canister in stand.get("canisters") or []:
        name = (canister.get("name") or "").strip()
        cid = (canister.get("canister_id") or "").strip()
        if name and cid:
            out[name] = cid
    return out


def _baton_query(
    baton_id: str,
    method: str,
    network: str,
    *,
    identity: str | None = None,
) -> Any:
    raw = _run_dfx(
        [baton_id, method, "()"],
        network=network,
        identity=identity,
        query=True,
    )
    text = _parse_candid_text(raw)
    return json.loads(text)


def poll_job_until_terminal(
    installer_id: str,
    job_id: str,
    network: str,
    *,
    identity: str | None = None,
    timeout_s: int = 900,
    interval_s: int = 10,
) -> dict[str, Any]:
    terminal = {
        "completed",
        "failed",
        "failed_verification",
        "cancelled",
    }
    elapsed = 0
    last: dict[str, Any] = {}
    while elapsed <= timeout_s:
        last = fetch_job_status(installer_id, job_id, network, identity=identity)
        status = (last.get("status") or "unknown").strip()
        _log(f"  [{elapsed:>4}s] job status: {status}")
        if status in terminal:
            return last
        time.sleep(interval_s)
        elapsed += interval_s
    raise E2EError(
        f"job {job_id} did not reach a terminal state within {timeout_s}s "
        f"(last status: {last.get('status')!r})"
    )


def assert_topology(
    *,
    tree: dict[str, Any],
    section: str,
    stand: str,
    job: dict[str, Any],
    casals_id: str,
    network: str,
    identity: str | None,
) -> str:
    stand_node = _find_stand(tree, section, stand)
    if stand_node is None:
        sections = [
            (sec.get("name"), [s.get("name") for s in sec.get("stands") or []])
            for sec in tree.get("sections") or []
        ]
        raise E2EError(
            f"stand '{stand}' not found under section '{section}' in get_tree; "
            f"sections={sections}"
        )

    names = _canister_map(stand_node)
    expected = {
        f"{stand}-backend": (job.get("backend_canister_id") or "").strip(),
        f"{stand}-frontend": (job.get("frontend_canister_id") or "").strip(),
        f"{stand}-baton": "",
    }
    for orch_name, job_id in expected.items():
        tree_id = names.get(orch_name, "")
        if not tree_id:
            raise E2EError(
                f"get_tree missing canister '{orch_name}' on stand '{stand}'; "
                f"have {sorted(names)}"
            )
        if job_id and tree_id != job_id:
            raise E2EError(
                f"{orch_name}: get_tree id {tree_id} != job status id {job_id}"
            )

    baton_id = names[f"{stand}-baton"]
    if not baton_id:
        raise E2EError(f"baton canister id empty for stand '{stand}'")

    backend_id = names[f"{stand}-backend"]
    frontend_id = names[f"{stand}-frontend"]
    managed = _baton_query(baton_id, "list_managed_canisters", network, identity=identity)
    if not isinstance(managed, list):
        raise E2EError(f"baton list_managed_canisters expected list, got {managed!r}")
    managed_set = set(managed)
    for cid in (backend_id, frontend_id):
        if cid not in managed_set:
            raise E2EError(
                f"baton {baton_id} list_managed_canisters missing {cid}; managed={managed}"
            )

    config = _baton_query(baton_id, "get_config", network, identity=identity)
    if not isinstance(config, dict):
        raise E2EError(f"baton get_config expected object, got {config!r}")
    policy = config.get("upgrade_approval_policy") or {}
    if not isinstance(policy, dict):
        raise E2EError(f"upgrade_approval_policy not an object: {policy!r}")
    threshold = int(policy.get("threshold") or 0)
    eligible = policy.get("eligible") or []
    required = policy.get("required") or []
    if threshold < 2 and not eligible and not required:
        raise E2EError(
            f"baton upgrade policy looks unset: {policy}"
        )
    if threshold < 1:
        raise E2EError(f"baton upgrade policy threshold must be >= 1: {policy}")

    _log(
        f"  topology ok: stand={stand} backend={backend_id} "
        f"frontend={frontend_id} baton={baton_id} policy_threshold={threshold}"
    )
    return baton_id


def _dump_diagnostics(
    *,
    installer_id: str,
    casals_id: str,
    job_id: str,
    network: str,
    identity: str | None,
) -> None:
    _log("--- diagnostics: deployment job status ---")
    try:
        job = fetch_job_status(installer_id, job_id, network, identity=identity)
        _log(json.dumps(job, indent=2, sort_keys=True))
    except Exception as exc:
        _log(f"  (could not fetch job status: {exc})")
    _log("--- diagnostics: casals get_tree ---")
    try:
        tree = fetch_casals_tree(casals_id, network, identity=identity)
        _log(json.dumps(tree, indent=2, sort_keys=True))
    except Exception as exc:
        _log(f"  (could not fetch get_tree: {exc})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Provision one local realm and assert Casals/baton topology.",
    )
    parser.add_argument(
        "--descriptor",
        default="environments/local.json",
        help="GaaS environment descriptor written by gaas new",
    )
    parser.add_argument("--network", default="local")
    parser.add_argument("--identity", default=None)
    parser.add_argument(
        "--realm-name",
        default="GaaSE2ERealm",
        help="Human-readable realm name (slug derived from this)",
    )
    parser.add_argument("--poll-timeout", type=int, default=900, help="seconds")
    parser.add_argument("--poll-interval", type=int, default=10, help="seconds")
    args = parser.parse_args(argv)

    descriptor = load_descriptor(args.descriptor)
    canisters = descriptor["canisters"]
    registry_id = canisters["realm_registry_backend"]
    installer_id = canisters["realm_installer"]
    casals_id = canisters["casals_backend"]

    manifest = build_manifest(descriptor, realm_name=args.realm_name, network=args.network)
    stand = manifest["casals"]["stand"]
    section = manifest["casals"]["section"]

    _log("=== GaaS local realm / baton topology E2E ===")
    _log(f"  network={args.network} registry={registry_id} installer={installer_id}")
    _log(f"  casals={casals_id} stand={stand}")

    job_id = ""
    try:
        job_id = request_deployment(
            registry_id, manifest, args.network, identity=args.identity
        )
        job = poll_job_until_terminal(
            installer_id,
            job_id,
            args.network,
            identity=args.identity,
            timeout_s=args.poll_timeout,
            interval_s=args.poll_interval,
        )
        status = (job.get("status") or "").strip()
        if status != "completed":
            error = (job.get("error") or "").strip()
            raise E2EError(
                f"deployment job ended with status '{status}'"
                + (f": {error}" if error else "")
            )

        tree = fetch_casals_tree(casals_id, args.network, identity=args.identity)
        baton_id = assert_topology(
            tree=tree,
            section=section,
            stand=stand,
            job=job,
            casals_id=casals_id,
            network=args.network,
            identity=args.identity,
        )

        _log("=== PASS: realm provisioned; Casals stand + baton topology verified ===")
        _log(f"  job_id={job_id} baton_canister_id={baton_id}")
        return 0
    except E2EError as exc:
        _log(f"=== FAIL: {exc} ===")
        if job_id:
            _dump_diagnostics(
                installer_id=installer_id,
                casals_id=casals_id,
                job_id=job_id,
                network=args.network,
                identity=args.identity,
            )
        return 1


if __name__ == "__main__":
    sys.exit(main())
