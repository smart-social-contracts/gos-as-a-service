"""Tests for gaas-env.json generation (build-time frontend config)."""

from gaas.descriptor import Descriptor
from gaas.gaas_env import build_gaas_env


def _descriptor() -> Descriptor:
    return Descriptor.model_validate(
        {
            "name": "test",
            "domain": "test.gos.earth",
            "gos": [
                {
                    "implementation": "realms-gos",
                    "version": "v0.4.0",
                    "release_repo": "smart-social-contracts/realms",
                    "artifacts": {
                        "backend_wasm_key": "realm-backend",
                        "frontend_wasm_key": "realm-assets",
                    },
                    "loader_profile": "realms-iframe-v1",
                }
            ],
            "canisters": {
                "realm_registry_backend": "yhw3g-fyaaa-aaaas-qgorq-cai",
                "realm_registry_frontend": "qtank-3qaaa-aaaaa-qhb6q-cai",
            },
            "casals": {"version": "v0.3.1"},
        }
    )


def test_canisters_are_name_first_for_network_js():
    env = build_gaas_env(_descriptor(), "ic")
    # network.js getCanisterId resolves gaasEnv.canisters[name][network]
    assert env["canisters"]["realm_registry_backend"]["ic"] == "yhw3g-fyaaa-aaaas-qgorq-cai"
    assert env["canisters"]["realm_registry_frontend"]["ic"] == "qtank-3qaaa-aaaaa-qhb6q-cai"
    # staging.gos.earth detects "staging" even when gaas new used --network ic
    assert env["canisters"]["realm_registry_backend"]["test"] == "yhw3g-fyaaa-aaaas-qgorq-cai"
    assert env["canisters"]["realm_registry_frontend"]["test"] == "qtank-3qaaa-aaaaa-qhb6q-cai"


def test_ii_alternative_origins_include_frontend_raw_origin():
    env = build_gaas_env(_descriptor(), "ic")
    assert "https://qtank-3qaaa-aaaaa-qhb6q-cai.icp0.io" in env["ii_alternative_origins"]


def test_domain_and_network_propagate():
    env = build_gaas_env(_descriptor(), "ic")
    assert env["domain"] == "test.gos.earth"
    assert env["network"] == "ic"


def test_flags_omitted_when_empty():
    env = build_gaas_env(_descriptor(), "ic")
    assert "flags" not in env


def test_flags_included_when_set():
    desc = _descriptor()
    desc.flags["can_test_mode"] = True
    env = build_gaas_env(desc, "ic")
    assert env["flags"] == {"can_test_mode": True}
