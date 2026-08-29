"""GET /version contract tests (gos-as-a-service#39).

Every GaaS-owned backend serves build provenance at /version over the IC
HTTP interface (http_request + http_request_update). Values are stamped at
build/release time; unstamped placeholders (local/dev builds) are omitted
honestly.
"""

import importlib.util
import json
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from realm_registry_backend.api import status as registry_status  # noqa: E402
import version_http as installer_version_http  # noqa: E402


def _load_file_registry_main():
    path = os.path.join(_REPO_ROOT, "src", "file_registry", "main.py")
    spec = importlib.util.spec_from_file_location("file_registry_main_version", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["file_registry_main_version"] = module
    spec.loader.exec_module(module)
    return module


file_registry_main = _load_file_registry_main()

_REQ = {"method": "GET", "url": "/version", "headers": [], "body": b""}


def _headers_dict(resp):
    return {k: v for k, v in resp["headers"]}


def _assert_contract(resp, canister_name):
    assert resp["status_code"] == 200
    headers = _headers_dict(resp)
    assert headers["Content-Type"] == "application/json"
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert headers["Cache-Control"] == "no-cache, must-revalidate"
    payload = json.loads(resp["body"].decode("utf-8"))
    assert payload["canister"] == canister_name
    return payload


def _assert_unstamped_omits(payload):
    # Repo checkout is unstamped: placeholder-backed fields are omitted.
    assert "sha" not in payload
    assert "built_at" not in payload
    assert "version" not in payload


# ── realm_registry_backend ─────────────────────────────────────────────


def test_registry_version_ok_unstamped():
    resp = registry_status.version_http_response(dict(_REQ))
    payload = _assert_contract(resp, "realm_registry_backend")
    _assert_unstamped_omits(payload)


def test_registry_version_strips_query_string():
    resp = registry_status.version_http_response({**_REQ, "url": "/version?foo=bar"})
    assert resp["status_code"] == 200


def test_registry_version_404_other_paths():
    resp = registry_status.version_http_response({**_REQ, "url": "/status"})
    assert resp["status_code"] == 404
    assert _headers_dict(resp)["Content-Type"] == "application/json"


def test_registry_version_options_preflight():
    resp = registry_status.version_http_response({**_REQ, "method": "OPTIONS"})
    assert resp["status_code"] == 204


def test_registry_version_stamped_fields(monkeypatch):
    monkeypatch.setattr(registry_status, "_SHA_STAMP", "a1b2c3d")
    monkeypatch.setattr(registry_status, "_BUILT_AT_STAMP", "2026-08-29T13:04:05Z")
    monkeypatch.setattr(registry_status, "_VERSION_STAMP", "v0.4.0")
    payload = registry_status.get_version_payload()
    assert payload == {
        "canister": "realm_registry_backend",
        "sha": "a1b2c3d",
        "built_at": "2026-08-29T13:04:05Z",
        "version": "v0.4.0",
    }


# ── realm_installer ────────────────────────────────────────────────────


def test_installer_version_ok_unstamped():
    resp = installer_version_http.version_http_response(dict(_REQ))
    payload = _assert_contract(resp, "realm_installer")
    _assert_unstamped_omits(payload)


def test_installer_version_404_other_paths():
    resp = installer_version_http.version_http_response({**_REQ, "url": "/"})
    assert resp["status_code"] == 404


def test_installer_version_options_preflight():
    resp = installer_version_http.version_http_response({**_REQ, "method": "OPTIONS"})
    assert resp["status_code"] == 204


def test_installer_version_stamped_fields(monkeypatch):
    monkeypatch.setattr(installer_version_http, "_SHA_STAMP", "a1b2c3d")
    monkeypatch.setattr(installer_version_http, "_BUILT_AT_STAMP", "2026-08-29T13:04:05Z")
    payload = installer_version_http.get_version_payload()
    assert payload["sha"] == "a1b2c3d"
    assert payload["built_at"] == "2026-08-29T13:04:05Z"
    assert "version" not in payload  # VERSION_STAMP left unstamped


# ── file_registry ──────────────────────────────────────────────────────


def test_file_registry_version_ok_unstamped():
    resp = file_registry_main._handle_http(dict(_REQ))
    payload = _assert_contract(resp, "file_registry")
    _assert_unstamped_omits(payload)


def test_file_registry_version_stamped_fields(monkeypatch):
    monkeypatch.setattr(file_registry_main, "_SHA_STAMP", "a1b2c3d")
    monkeypatch.setattr(file_registry_main, "_BUILT_AT_STAMP", "2026-08-29T13:04:05Z")
    payload = file_registry_main._version_payload()
    assert payload["sha"] == "a1b2c3d"
    assert payload["built_at"] == "2026-08-29T13:04:05Z"


def test_file_registry_existing_routes_untouched():
    # Root still lists namespaces; unknown paths still 404 through namespaces.
    resp = file_registry_main._handle_http({**_REQ, "url": "/"})
    assert resp["status_code"] == 200
    resp = file_registry_main._handle_http({**_REQ, "url": "/no/such/ns"})
    assert resp["status_code"] == 404
