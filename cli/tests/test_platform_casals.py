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


def test_local_backend_wasm_uses_basilisk_not_dfx_local(tmp_path: Path, monkeypatch) -> None:
    from gaas.platform import _local_backend_wasm

    canister = "realm_registry_backend"
    src_dir = tmp_path / "src" / canister
    src_dir.mkdir(parents=True)
    (src_dir / "main.py").write_text("# stub\n", encoding="utf-8")
    (src_dir / f"{canister}.did").write_text("service : {}\n", encoding="utf-8")
    seen: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        del kwargs
        seen["cmd"] = list(cmd)
        out = tmp_path / ".basilisk" / canister / f"{canister}.wasm"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"wasm")

    monkeypatch.setattr("gaas.platform.run_subprocess", fake_run)
    wasm = _local_backend_wasm(tmp_path, canister)
    assert wasm.read_bytes() == b"wasm"
    assert seen["cmd"][1:4] == ["-m", "basilisk", canister]
    assert "dfx" not in seen["cmd"]
