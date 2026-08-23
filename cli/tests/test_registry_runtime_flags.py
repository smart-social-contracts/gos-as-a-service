import json

from gaas.descriptor import Descriptor
from gaas.phases import _registry_runtime_config_json, verify_registry_runtime_flags


def _descriptor(name: str) -> Descriptor:
    return Descriptor.model_validate(
        {
            "version": 1,
            "name": name,
            "domain": f"{name}.gos.earth",
            "flags": {"can_test_mode": True},
            "services": {"billing_url": "https://billing.example.dev"},
            "casals": {"version": "main", "release_repo": "smart-social-contracts/Casals"},
            "gos": [
                {
                    "implementation": "realms-gos",
                    "version": "main",
                    "release_repo": "smart-social-contracts/realms",
                    "artifacts": {
                        "backend_wasm_key": "realm-backend",
                        "frontend_wasm_key": "realm-assets",
                    },
                    "loader_profile": "realms-iframe-v1",
                }
            ],
            "canisters": {},
        }
    )


def test_only_test_env_bypasses_internet_identity():
    staging = json.loads(_registry_runtime_config_json(_descriptor("staging"), "ic"))
    assert staging["test_flags"] == {"test_mode": True, "ii_bypass": False}

    test = json.loads(_registry_runtime_config_json(_descriptor("test"), "ic"))
    assert test["test_flags"]["ii_bypass"] is True


def test_verify_runtime_flags_accepts_disabled_ii_bypass():
    runtime_json = json.dumps({"test_flags": {"test_mode": True, "ii_bypass": False}})
    flags = {"test_mode": True, "test_mode_ii_bypass": False}
    assert verify_registry_runtime_flags(runtime_json, flags) == []


def test_verify_runtime_flags_reports_each_mismatch():
    runtime_json = json.dumps({"test_flags": {"test_mode": True, "ii_bypass": False}})
    flags = {"test_mode": False, "test_mode_ii_bypass": True}
    assert sorted(verify_registry_runtime_flags(runtime_json, flags)) == [
        "test_mode",
        "test_mode_ii_bypass",
    ]
