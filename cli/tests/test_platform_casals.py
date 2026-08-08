"""Tests for Casals frontend build-time canister ID wiring."""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

from gaas.platform import (
    _casals_ic_env_cookie_value,
    _inject_casals_ic_env_assets,
)

CONDUCTOR_ID = "qthgp-3yaaa-aaaae-agveq-cai"
FRONTEND_ID = "qic2k-baaaa-aaaae-agvga-cai"


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
