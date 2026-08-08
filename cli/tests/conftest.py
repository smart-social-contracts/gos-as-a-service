"""Shared test fixtures."""

from __future__ import annotations

import pytest

import gaas.dfx as _dfx


@pytest.fixture(autouse=True)
def _no_real_dfx_calls(monkeypatch):
    """Hard-block any real dfx subprocess call during tests.

    A test that forgets to mock a client helper (e.g. upload_file) would
    otherwise shell out to dfx against whatever network/identity the
    arguments name — including mainnet canisters. Tests that exercise
    dfx internals re-mock ``gaas.dfx._run`` themselves, which overrides
    this guard.
    """

    def _blocked(args, **kwargs):
        raise RuntimeError(
            f"test attempted a real dfx call: {args!r}. "
            "Mock the client helper or gaas.dfx._run instead."
        )

    monkeypatch.setattr(_dfx, "_run", _blocked)

SAMPLE_DESCRIPTOR = {
    "version": 1,
    "name": "test",
    "domain": "test.gos.earth",
    "gos": [
        {
            "implementation": "realms-gos",
            "version": "v0.3.1",
            "release_repo": "smart-social-contracts/realms",
            "artifacts": {
                "backend_wasm_key": "realm-backend",
                "frontend_wasm_key": "realm-assets",
            },
            "loader_profile": "realms-iframe-v1",
        }
    ],
    "canisters": {},
    "casals": {
        "version": "v0.3.0",
        "release_repo": "smart-social-contracts/Casals",
    },
    "services": {},
    "dns": {"provider": "manual"},
}

VALID_CANISTER_ID = "yhw3g-fyaaa-aaaas-qgorq-cai"
