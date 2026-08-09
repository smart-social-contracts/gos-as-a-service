"""Unit tests for file_registry namespace approval."""

from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import time
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))

import _cdk as basilisk  # noqa: E402

mock_ic = MagicMock()
mock_ic.time.return_value = int(time.time() * 1_000_000_000)
basilisk.ic = mock_ic

import file_registry.main as fr  # noqa: E402

fr.ic = mock_ic


@pytest.fixture
def registry_root(tmp_path, monkeypatch):
    root = tmp_path / "registry"
    root.mkdir()
    monkeypatch.setattr(fr, "REGISTRY_DIR", str(root))
    monkeypatch.setattr(fr, "CHUNKS_DIR", str(root / "_chunks"))
    monkeypatch.setattr(fr, "NAMESPACES_FILE", str(root / "_namespaces.json"))
    monkeypatch.setattr(fr, "ACL_FILE", str(root / "_acl.json"))
    monkeypatch.setattr(fr, "APPROVALS_FILE", str(root / "_approvals.json"))
    monkeypatch.setattr(fr, "_file_path", lambda ns, path: os.path.join(str(root), ns, path.lstrip("/")))
    monkeypatch.setattr(fr, "_meta_path", lambda ns: os.path.join(str(root), ns, "_meta.json"))
    return root


def _as_controller(principal: str = "controller-principal"):
    mock_ic.caller.return_value.to_str.return_value = principal
    mock_ic.is_controller.return_value = True


def _as_publisher(principal: str = "publisher-principal"):
    mock_ic.caller.return_value.to_str.return_value = principal
    mock_ic.is_controller.return_value = False


def _store(namespace: str, path: str, content: bytes, *, principal: str = "publisher-principal"):
    _as_publisher(principal)
    payload = json.dumps(
        {
            "namespace": namespace,
            "path": path,
            "content_b64": base64.b64encode(content).decode("ascii"),
        }
    )
    result = json.loads(fr.store_file(payload))
    assert result.get("ok") is True, result
    fr.publish_namespace(json.dumps({"namespace": namespace}))
    return result


def test_set_get_approval_flow(registry_root):
    ns = "ext/syntropia/0.8.9"
    _store(ns, "manifest.json", b'{"id":"syntropia"}')

    _as_controller("deployer-principal")
    set_result = json.loads(
        fr.set_namespace_approval(json.dumps({"namespace": ns, "notes": "seeded"}))
    )
    assert set_result["ok"] is True
    assert set_result["status"] == "approved"
    assert set_result["approver"] == "deployer-principal"

    approval = json.loads(fr.get_namespace_approval_icc(ns))
    assert approval["approved"] is True
    assert approval["status"] == "approved"
    assert approval["approver"] == "deployer-principal"
    assert approval["notes"] == "seeded"
    assert approval["content_matches"] is True
    assert approval["file_count"] == 1


def test_unknown_namespace_returns_error(registry_root):
    result = json.loads(fr.get_namespace_approval(json.dumps({"namespace": "ext/nope/1.0.0"})))
    assert "error" in result


def test_unapproved_namespace(registry_root):
    ns = "ext/foo/1.0.0"
    _store(ns, "manifest.json", b"{}")

    approval = json.loads(fr.get_namespace_approval(json.dumps({"namespace": ns})))
    assert approval["approved"] is False
    assert approval["status"] == "unapproved"


def test_content_change_invalidates_approval(registry_root):
    ns = "ext/a/1.0.0"
    _store(ns, "backend/entry.py", b"v1")

    _as_controller("approver")
    fr.set_namespace_approval(json.dumps({"namespace": ns}))
    assert json.loads(fr.get_namespace_approval_icc(ns))["approved"] is True

    _store(ns, "backend/entry.py", b"v2")
    approval = json.loads(fr.get_namespace_approval_icc(ns))
    assert approval["approved"] is False
    assert approval["status"] == "unapproved"


def test_delete_file_invalidates_approval(registry_root):
    ns = "ext/a/1.0.0"
    _store(ns, "backend/a.py", b"a")
    _store(ns, "backend/b.py", b"b")

    _as_controller("approver")
    fr.set_namespace_approval(json.dumps({"namespace": ns}))

    _as_publisher()
    fr.delete_file(json.dumps({"namespace": ns, "path": "backend/b.py"}))
    approval = json.loads(fr.get_namespace_approval_icc(ns))
    assert approval["approved"] is False
    assert approval["status"] == "unapproved"


def test_rejected_status(registry_root):
    ns = "ext/a/1.0.0"
    _store(ns, "manifest.json", b"{}")

    _as_controller("approver")
    fr.set_namespace_approval(
        json.dumps({"namespace": ns, "status": "rejected", "notes": "bad imports"})
    )
    approval = json.loads(fr.get_namespace_approval_icc(ns))
    assert approval["approved"] is False
    assert approval["status"] == "rejected"
    assert approval["notes"] == "bad imports"


def test_non_approver_rejected(registry_root):
    ns = "ext/a/1.0.0"
    _store(ns, "manifest.json", b"{}")

    _as_publisher("random-user")
    result = json.loads(fr.set_namespace_approval(json.dumps({"namespace": ns})))
    assert "error" in result
