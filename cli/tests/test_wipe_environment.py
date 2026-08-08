"""Local parsing tests for wipe_environment (no network)."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import sys
from pathlib import Path

from gaas.dfx import parse_module_hash

REPO_ROOT = Path(__file__).resolve().parents[2]
WIPE_SCRIPT = REPO_ROOT / "scripts" / "wipe_environment.py"


def _load_wipe_module():
    spec = importlib.util.spec_from_file_location("wipe_environment", WIPE_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["wipe_environment"] = module
    spec.loader.exec_module(module)
    return module


def test_parse_module_hash_with_hex():
    raw = (
        "Canister status call result for yhw3g-fyaaa-aaaas-qgorq-cai.\n"
        "Status: Running\n"
        "Module hash: 0x741eb0574ba7f26a96b3de6deb9e7d45610154ee679b3be5d97938c696a98d7c\n"
    )
    assert (
        parse_module_hash(raw)
        == "0x741eb0574ba7f26a96b3de6deb9e7d45610154ee679b3be5d97938c696a98d7c"
    )


def test_parse_module_hash_none():
    raw = "Status: Running\nModule hash: None\n"
    assert parse_module_hash(raw) is None


def test_parse_module_hash_missing():
    assert parse_module_hash("Status: Running\n") is None


def test_blank_wasm_reproducible():
    wipe = _load_wipe_module()
    wasm_path, module_hash = wipe.materialize_blank_wasm()
    try:
        data = wasm_path.read_bytes()
        assert base64.b64decode(wipe.BLANK_WASM_B64) == data
        assert hashlib.sha256(data).hexdigest() == wipe.KNOWN_BLANK_WASM_SHA256
        assert module_hash == wipe.KNOWN_BLANK_MODULE_HASH
    finally:
        wasm_path.unlink(missing_ok=True)


def test_load_canisters_from_descriptor(tmp_path):
    wipe = _load_wipe_module()
    descriptor = tmp_path / "env.json"
    descriptor.write_text(
        """
{
  "version": 1,
  "name": "demo",
  "domain": "demo.example.com",
  "gos": [{
    "implementation": "realms-gos",
    "version": "main",
    "release_repo": "smart-social-contracts/realms",
    "artifacts": {
      "backend_wasm_key": "realm-backend",
      "frontend_wasm_key": "realm-assets"
    },
    "loader_profile": "realms-iframe-v1"
  }],
  "canisters": {
    "realm_registry_backend": "yhw3g-fyaaa-aaaas-qgorq-cai",
    "file_registry": "uq2mu-kaaaa-aaaah-avqcq-cai"
  },
  "casals": {
    "version": "main",
    "release_repo": "smart-social-contracts/Casals"
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    all_canisters = wipe.load_canisters(descriptor, ())
    assert set(all_canisters) == {"realm_registry_backend", "file_registry"}

    subset = wipe.load_canisters(descriptor, ("file_registry",))
    assert subset == {"file_registry": "uq2mu-kaaaa-aaaah-avqcq-cai"}
