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

CASALS_BOOTSTRAP_TEST_IDS = {
    "casals_backend": "qthgp-3yaaa-aaaae-agveq-cai",
    "casals_frontend": "qic2k-baaaa-aaaae-agvga-cai",
    "casals_file_registry": "uq2mu-kaaaa-aaaah-avqcq-cai",
    "casals_file_registry_frontend": "qbbef-6qaaa-aaaap-quwoa-cai",
}


def mock_run_casals_new(descriptor, **kwargs):
    """Patch target for gaas.phases.run_casals_new in create-canister tests."""
    had = any(
        (descriptor.canisters.get(name) or "").strip()
        for name in CASALS_BOOTSTRAP_TEST_IDS
    )
    for name, default_id in CASALS_BOOTSTRAP_TEST_IDS.items():
        existing = (descriptor.canisters.get(name) or "").strip()
        descriptor.set_canister_id(name, existing or default_id)
    return {
        "ok": True,
        "mode": "upgrade" if had else "create",
        "canisters": {
            "casals_backend": descriptor.canisters["casals_backend"],
            "casals_frontend": descriptor.canisters["casals_frontend"],
            "ic_file_registry": descriptor.canisters["casals_file_registry"],
            "ic_file_registry_frontend": descriptor.canisters[
                "casals_file_registry_frontend"
            ],
        },
        "seeded": False,
    }
