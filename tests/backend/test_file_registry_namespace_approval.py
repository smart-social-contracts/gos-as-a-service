"""file_registry namespace approval helpers (marketplace install gate)."""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

# Load main.py without pulling the full canister runtime.
_main_path = Path(__file__).resolve().parents[2] / "src" / "file_registry" / "main.py"
_spec = importlib.util.spec_from_file_location("file_registry_main", _main_path)
_main = importlib.util.module_from_spec(_spec)
sys.modules["file_registry_main"] = _main
_spec.loader.exec_module(_main)


def _with_temp_registry():
    tmpdir = tempfile.mkdtemp()
    orig = {
        "REGISTRY_DIR": _main.REGISTRY_DIR,
        "APPROVALS_FILE": _main.APPROVALS_FILE,
        "CHUNKS_DIR": _main.CHUNKS_DIR,
    }
    _main.REGISTRY_DIR = tmpdir
    _main.APPROVALS_FILE = os.path.join(tmpdir, "_approvals.json")
    _main.CHUNKS_DIR = os.path.join(tmpdir, "_chunks")
    return orig


def _restore_registry(orig):
    _main.REGISTRY_DIR = orig["REGISTRY_DIR"]
    _main.APPROVALS_FILE = orig["APPROVALS_FILE"]
    _main.CHUNKS_DIR = orig["CHUNKS_DIR"]


def test_unapproved_namespace_payload():
    orig = _with_temp_registry()
    try:
        payload = _main._approval_get_payload("ext/voting/1.0.0", None)
        assert payload["approved"] is False
        assert payload["status"] == "unapproved"
        assert payload["namespace"] == "ext/voting/1.0.0"
    finally:
        _restore_registry(orig)


def test_approved_payload_requires_matching_hashes():
    orig = _with_temp_registry()
    try:
        ns = "ext/voting/1.0.0"
        _main._save_meta(ns, {
            "files": {
                "manifest.json": {"sha256": "abc123", "size": 1},
            },
        })
        record = {
            "status": "approved",
            "approver": "l5qpy-wqaaa-aaaah-qu2mq-cai",
            "approved_at": 123,
            "file_hashes": {"manifest.json": "abc123"},
        }
        payload = _main._approval_get_payload(ns, record)
        assert payload["approved"] is True
        assert payload["content_matches"] is True
        assert payload["approver"] == "l5qpy-wqaaa-aaaah-qu2mq-cai"
        assert payload["file_count"] == 1
    finally:
        _restore_registry(orig)


def test_stale_approval_not_effective():
    orig = _with_temp_registry()
    try:
        ns = "ext/voting/1.0.0"
        _main._save_meta(ns, {
            "files": {
                "manifest.json": {"sha256": "changed", "size": 1},
            },
        })
        record = {
            "status": "approved",
            "approver": "l5qpy-wqaaa-aaaah-qu2mq-cai",
            "approved_at": 123,
            "file_hashes": {"manifest.json": "abc123"},
        }
        payload = _main._approval_get_payload(ns, record)
        assert payload["approved"] is False
        assert payload["content_matches"] is False
        assert payload["status"] == "approved"
    finally:
        _restore_registry(orig)


def test_save_and_load_approvals():
    orig = _with_temp_registry()
    try:
        data = {
            "ext/voting/1.0.0": {
                "status": "approved",
                "file_hashes": {"manifest.json": "abc"},
            },
        }
        _main._save_approvals(data)
        assert _main._load_approvals() == data
    finally:
        _restore_registry(orig)


def test_list_namespaces_includes_approved_flag():
    orig = _with_temp_registry()
    orig_ns = _main.NAMESPACES_FILE
    try:
        _main.NAMESPACES_FILE = os.path.join(_main.REGISTRY_DIR, "_namespaces.json")
        ns = "ext/voting/1.0.0"
        _main._save_namespaces({
            ns: {"namespace": ns, "created": 0, "owner": "x", "description": ""},
        })
        _main._save_meta(ns, {
            "files": {"manifest.json": {"sha256": "abc123", "size": 1}},
        })
        listing = json.loads(_main.list_namespaces())
        assert listing[0]["namespace"] == ns
        assert listing[0]["approved"] is False
        assert listing[0]["content_matches"] is None

        _main._save_approvals({
            ns: {
                "status": "approved",
                "file_hashes": {"manifest.json": "abc123"},
            },
        })
        listing = json.loads(_main.list_namespaces())
        assert listing[0]["approved"] is True
        assert listing[0]["content_matches"] is True
    finally:
        _main.NAMESPACES_FILE = orig_ns
        _restore_registry(orig)


def test_get_namespace_approval_icc_delegates():
    orig = _with_temp_registry()
    try:
        raw = _main.get_namespace_approval_icc("ext/voting/1.0.0")
        import json

        payload = json.loads(raw)
        assert payload["namespace"] == "ext/voting/1.0.0"
        assert payload["approved"] is False
    finally:
        _restore_registry(orig)


def test_publish_then_marketplace_stamp_is_approved_for_hash():
    """First-party ext/ publish + marketplace stamp → approved and content_matches."""
    from unittest.mock import MagicMock

    orig = _with_temp_registry()
    orig_ns = _main.NAMESPACES_FILE
    orig_acl = _main.ACL_FILE
    orig_ic = _main.ic
    try:
        _main.NAMESPACES_FILE = os.path.join(_main.REGISTRY_DIR, "_namespaces.json")
        _main.ACL_FILE = os.path.join(_main.REGISTRY_DIR, "_acl.json")
        fake_ic = MagicMock()
        fake_ic.caller.return_value.to_str.return_value = "marketplace-principal"
        fake_ic.time.return_value = 1_000
        fake_ic.is_controller.return_value = True
        _main.ic = fake_ic

        ns = "ext/voting/1.0.0"
        store = json.loads(
            _main.store_file(
                json.dumps(
                    {
                        "namespace": ns,
                        "path": "manifest.json",
                        "content_b64": __import__("base64").b64encode(
                            b'{"id":"voting"}'
                        ).decode("ascii"),
                    }
                )
            )
        )
        assert store.get("ok") is True
        published_hash = store["sha256"]

        published = json.loads(_main.publish_namespace(json.dumps({"namespace": ns})))
        assert published.get("ok") is True

        unstamped = json.loads(_main.get_namespace_approval(json.dumps({"namespace": ns})))
        assert unstamped["approved"] is False
        assert unstamped["status"] == "unapproved"

        stamped = json.loads(
            _main.set_namespace_approval(
                json.dumps({"namespace": ns, "status": "approved", "notes": "first-party"})
            )
        )
        assert stamped.get("ok") is True

        payload = json.loads(_main.get_namespace_approval(json.dumps({"namespace": ns})))
        assert payload["approved"] is True
        assert payload["content_matches"] is True
        assert payload["approver"] == "marketplace-principal"
        assert _main._current_file_hashes(ns)["manifest.json"] == published_hash

        listing = json.loads(_main.list_namespaces())
        assert listing[0]["namespace"] == ns
        assert listing[0]["approved"] is True
        assert listing[0]["content_matches"] is True

        # Republish (new bytes) invalidates the hash-bound stamp.
        json.loads(
            _main.store_file(
                json.dumps(
                    {
                        "namespace": ns,
                        "path": "manifest.json",
                        "content_b64": __import__("base64").b64encode(
                            b'{"id":"voting","v":2}'
                        ).decode("ascii"),
                    }
                )
            )
        )
        stale = json.loads(_main.get_namespace_approval(json.dumps({"namespace": ns})))
        assert stale["approved"] is False
        assert stale["content_matches"] is False
        assert stale["status"] == "approved"

        json.loads(
            _main.set_namespace_approval(
                json.dumps({"namespace": ns, "status": "approved", "notes": "restamp"})
            )
        )
        restamped = json.loads(_main.get_namespace_approval(json.dumps({"namespace": ns})))
        assert restamped["approved"] is True
        assert restamped["content_matches"] is True
    finally:
        _main.ic = orig_ic
        _main.NAMESPACES_FILE = orig_ns
        _main.ACL_FILE = orig_acl
        _restore_registry(orig)
