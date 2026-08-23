"""file_registry namespace approval helpers (marketplace install gate)."""

import importlib.util
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
