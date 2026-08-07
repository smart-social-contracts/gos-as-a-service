#!/usr/bin/env python3
"""Integration tests for ``realm_installer`` candid surface.

Exercises core query endpoints on a live replica.  The old on-chain
``deploy_realm`` / ``get_deploy_status`` / ``list_deploys`` API has been
removed; the queue + ``report_canister_ready`` flow is the supported
path for full realm deploys.

If ``realm_installer`` is not deployed, the suite skips cleanly with
exit code 0.
"""

import json
import subprocess
import sys
import traceback


def _dfx_canister_id(canister: str) -> str:
    """Return the canister id, or the empty string if not deployed."""
    try:
        cp = subprocess.run(
            ["dfx", "canister", "id", canister],
            capture_output=True, text=True, timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return (cp.stdout or "").strip() if cp.returncode == 0 else ""


def _dfx_call(
    method: str, arg: str, *, query: bool = False, timeout: int = 60, output_json: bool = True,
):
    cmd = ["dfx", "canister", "call", "realm_installer", method, arg]
    if query:
        cmd.append("--query")
    if output_json:
        cmd.extend(["--output", "json"])
    cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return cp.stdout.strip(), cp.returncode, (cp.stderr or "").strip()


def _unwrap(out: str) -> str:
    """Strip the ``("…",)`` candid wrapper around a single text reply."""
    raw = out.strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1].strip()
    if raw.endswith(","):
        raw = raw[:-1].strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    return (
        raw.replace("\\\\", "\\")
        .replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_candid_surface_has_core_methods():
    """Sanity check: candid exposes queue + health (not removed deploy_realm)."""
    print("  - test_candid_surface_has_core_methods...", end=" ")
    out, code, err = _dfx_call(
        "__get_candid_interface_tmp_hack", "()", query=True, output_json=False,
    )
    assert code == 0, f"candid query failed: {err}"
    body = _unwrap(out)
    for needed in ("enqueue_deployment", "report_canister_ready", "destroy_realm_job", "health"):
        assert needed in body, f"missing endpoint in candid: {needed}"
    assert "deploy_realm" not in body, "deploy_realm should be removed from candid"
    print("✓")


def test_health_returns_ok():
    """``health`` returns ok: true."""
    print("  - test_health_returns_ok...", end=" ")
    out, code, err = _dfx_call("health", "()", query=True)
    assert code == 0, f"health failed: {err}"
    body = json.loads(out)
    assert body.get("ok") is True, body
    print("✓")


def test_list_deployment_jobs_returns_structured_payload():
    """``list_deployment_jobs`` returns a Candid ``Ok`` payload with ``jobs``."""
    print("  - test_list_deployment_jobs_returns_structured_payload...", end=" ")
    out, code, err = _dfx_call("list_deployment_jobs", "()", query=True)
    assert code == 0, f"list_deployment_jobs failed: {err}"
    body = json.loads(out)
    assert "Ok" in body, f"expected variant Ok, got: {body}"
    ok = body["Ok"]
    assert "jobs" in ok and isinstance(ok["jobs"], list), (
        f"jobs field missing/invalid: {ok}"
    )
    print(f"✓ (jobs={len(ok['jobs'])})")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("Testing realm_installer API surface:")

    if not _dfx_canister_id("realm_installer"):
        print("  ⚠️  realm_installer not deployed; skipping suite.")
        print("✅ Skipped (no realm_installer canister in this dfx project)")
        sys.exit(0)

    tests = [
        test_candid_surface_has_core_methods,
        test_health_returns_ok,
        test_list_deployment_jobs_returns_structured_payload,
    ]

    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print("✗")
            print(f"    Error: {e}")
            print("    Traceback:")
            traceback.print_exc()
            failed += 1

    print()
    if failed == 0:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print(f"❌ {failed} test(s) failed")
        sys.exit(1)
