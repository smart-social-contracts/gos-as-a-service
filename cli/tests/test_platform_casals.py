"""Tests for Casals frontend build-time canister ID wiring."""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

from gaas.ic_assets import merge_casals_ic_assets, merge_connect_src, url_to_origin
from gaas.platform import (
    _casals_frontend_cache_usable,
    _casals_ic_env_cookie_value,
    _inject_casals_ic_env_assets,
    _portal_ic_env_cookie_value,
    inject_portal_ic_env_assets,
)

CONDUCTOR_ID = "qthgp-3yaaa-aaaae-agveq-cai"
FRONTEND_ID = "qic2k-baaaa-aaaae-agvga-cai"

_CASALS_ASSETS = """[
  {
    "match": "**/*",
    "security_policy": "standard",
    "headers": {
      "Cache-Control": "public, max-age=0, must-revalidate",
      "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline'; connect-src 'self' http://localhost:* https://icp0.io https://*.icp0.io https://icp-api.io https://*.ic0.app; img-src 'self' data:; object-src 'none'; frame-ancestors 'none';"
    }
  },
  {
    "match": "**/*",
    "headers": {
      "Permissions-Policy": "clipboard-read=(self), clipboard-write=(self)"
    }
  }
]
"""


def test_inject_portal_ic_env_assets_overrides_json5_comments(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / ".ic-assets.json5").write_text(
        '[\n  {\n    // comment\n    "match": "**/*",\n    "headers": {"Referrer-Policy": "same-origin"}\n  }\n]\n',
        encoding="utf-8",
    )
    inject_portal_ic_env_assets(
        dist,
        "mjrky-pyaaa-aaaah-qu27a-cai",
        "2zaor-5yaaa-aaaac-qbxaa-cai",
    )
    config = json.loads((dist / ".ic-assets.json5").read_text())
    cookie = config[0]["headers"]["Set-Cookie"]
    decoded = urllib.parse.unquote(cookie.split("=", 1)[1].split(";", 1)[0])
    assert "mjrky-pyaaa-aaaah-qu27a-cai" in decoded
    assert "rhw4p" not in decoded
    assert "2zaor-5yaaa-aaaac-qbxaa-cai" in decoded
    encoded = _portal_ic_env_cookie_value(
        "mjrky-pyaaa-aaaah-qu27a-cai", "2zaor-5yaaa-aaaac-qbxaa-cai"
    )
    assert encoded in cookie


def test_casals_ic_env_cookie_value_format() -> None:
    encoded = _casals_ic_env_cookie_value(CONDUCTOR_ID, FRONTEND_ID)
    decoded = urllib.parse.unquote(encoded)
    assert decoded.startswith("ic_root_key=")
    assert f"PUBLIC_CANISTER_ID:casals_backend={CONDUCTOR_ID}" in decoded
    assert f"PUBLIC_CANISTER_ID:casals_frontend={FRONTEND_ID}" in decoded


def test_inject_casals_ic_env_assets_writes_json5(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    _inject_casals_ic_env_assets(dist, CONDUCTOR_ID, FRONTEND_ID)
    path = dist / ".ic-assets.json5"
    assert path.is_file()
    config = json.loads(path.read_text())
    cookie = config[0]["headers"]["Set-Cookie"]
    assert cookie.startswith("ic_env=")
    assert "SameSite=Lax" in cookie


def test_url_to_origin_strips_monitor_path() -> None:
    assert (
        url_to_origin("https://casals.realmsops.dev/v1/realms-test")
        == "https://casals.realmsops.dev"
    )
    assert url_to_origin("") == ""


def test_merge_preserves_casals_csp_and_adds_cookie() -> None:
    cookie = "ic_env=abc; SameSite=Lax"
    out = merge_casals_ic_assets(_CASALS_ASSETS, cookie)
    config = json.loads(out)
    csp = config[0]["headers"]["Content-Security-Policy"]
    assert "connect-src 'self'" in csp
    assert "https://icp0.io" in csp
    assert config[0]["headers"]["Cache-Control"].startswith("public")
    assert config[1]["headers"]["Permissions-Policy"].startswith("clipboard-read")
    html_rule = next(r for r in config if r.get("match") == "**/*.{html,shtml}")
    assert html_rule["headers"]["Set-Cookie"] == cookie


def test_merge_adds_monitor_origin_to_connect_src() -> None:
    cookie = "ic_env=abc; SameSite=Lax"
    origin = "https://casals.realmsops.dev"
    out = merge_casals_ic_assets(
        _CASALS_ASSETS, cookie, "https://casals.realmsops.dev/v1/realms-test"
    )
    config = json.loads(out)
    csp = config[0]["headers"]["Content-Security-Policy"]
    assert origin in csp.split("connect-src", 1)[1].split(";", 1)[0]
    again = merge_casals_ic_assets(out, cookie, origin)
    assert again == out


def test_merge_empty_monitor_url_does_not_invent_csp() -> None:
    cookie = "ic_env=abc; SameSite=Lax"
    out = merge_casals_ic_assets("[]", cookie, "")
    config = json.loads(out)
    assert len(config) == 1
    assert "Content-Security-Policy" not in config[0]["headers"]
    assert config[0]["headers"]["Set-Cookie"] == cookie


def test_merge_connect_src_idempotent() -> None:
    csp = "default-src 'self'; connect-src 'self' https://icp0.io;"
    once = merge_connect_src(csp, "https://casals.realmsops.dev")
    twice = merge_connect_src(once, "https://casals.realmsops.dev")
    assert twice == once
    assert once.count("https://casals.realmsops.dev") == 1


def test_inject_merges_monitor_into_existing_casals_policy(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / ".ic-assets.json5").write_text(_CASALS_ASSETS, encoding="utf-8")
    _inject_casals_ic_env_assets(
        dist,
        CONDUCTOR_ID,
        FRONTEND_ID,
        monitor_url="https://casals.realmsops.dev/v1/realms-test",
    )
    config = json.loads((dist / ".ic-assets.json5").read_text(encoding="utf-8"))
    csp = config[0]["headers"]["Content-Security-Policy"]
    assert "https://casals.realmsops.dev" in csp
    assert "Permissions-Policy" in config[1]["headers"]
    html_rule = next(r for r in config if r.get("match") == "**/*.{html,shtml}")
    assert html_rule["headers"]["Set-Cookie"].startswith("ic_env=")


def test_cookie_only_cache_is_not_usable(tmp_path: Path) -> None:
    cached = tmp_path / "dist"
    cached.mkdir()
    (cached / "index.html").write_text("<html></html>", encoding="utf-8")
    (cached / ".ic-assets.json5").write_text(
        json.dumps(
            [
                {
                    "match": "**/*.{html,shtml}",
                    "headers": {"Set-Cookie": "ic_env=stale; SameSite=Lax"},
                }
            ]
        ),
        encoding="utf-8",
    )
    assert _casals_frontend_cache_usable(cached) is False


def test_casals_policy_cache_is_usable(tmp_path: Path) -> None:
    cached = tmp_path / "dist"
    cached.mkdir()
    (cached / ".ic-assets.json5").write_text(_CASALS_ASSETS, encoding="utf-8")
    assert _casals_frontend_cache_usable(cached) is True


def test_local_backend_wasm_packs_with_basilisk(tmp_path: Path, monkeypatch) -> None:
    from unittest.mock import MagicMock

    from gaas.platform import _local_backend_wasm

    entry = tmp_path / "src" / "realm_registry_backend" / "main.py"
    entry.parent.mkdir(parents=True)
    entry.write_text("pass\n", encoding="utf-8")
    wasm = tmp_path / ".basilisk" / "realm_registry_backend" / "realm_registry_backend.wasm"
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        wasm.parent.mkdir(parents=True)
        wasm.write_bytes(b"wasm")
        return MagicMock()

    monkeypatch.setattr("gaas.runlog.run_subprocess", fake_run)
    fake_py = tmp_path / ".venv-basilisk" / "bin" / "python"
    fake_py.parent.mkdir(parents=True)
    fake_py.write_text("", encoding="utf-8")

    got = _local_backend_wasm(tmp_path, "realm_registry_backend")
    assert got == wasm
    assert calls[0][0] == str(fake_py)
    assert calls[0][1:4] == ["-m", "basilisk", "realm_registry_backend"]
