"""Shared test fixtures."""

from __future__ import annotations

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
