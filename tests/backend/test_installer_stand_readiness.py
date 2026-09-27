"""Tests for the "wait until the conductor installed the stand" readiness helper."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from stand_readiness import (
    installed_stand_canisters,
    stand_build_gate,
    stand_readiness,
    stand_required_members,
)


def _tree(stand: str, canisters: list[dict]) -> dict:
    return {
        "sections": [
            {"name": "Infra", "stands": [{"name": "platform", "canisters": [
                {"name": "file-registry", "canister_id": "fr-1", "status": "installed"},
            ]}]},
            {"name": "Deployments", "stands": [{"name": stand, "canisters": canisters}]},
        ]
    }


def test_required_members_are_backend_and_frontend():
    assert stand_required_members("alpha") == ["alpha-backend", "alpha-frontend"]


def test_created_but_not_installed_is_not_ready():
    tree = _tree("alpha", [
        {"name": "alpha-baton", "canister_id": "b-1", "status": "installed"},
        {"name": "alpha-backend", "canister_id": "be-1", "status": "created"},
        {"name": "alpha-frontend", "canister_id": "", "status": "pending"},
    ])
    ready, missing = stand_readiness(tree, "alpha", stand_required_members("alpha"))
    assert ready == {"alpha-baton": "b-1"}
    assert missing == ["alpha-backend", "alpha-frontend"]


def test_ready_when_every_required_member_is_installed():
    tree = _tree("alpha", [
        {"name": "alpha-baton", "canister_id": "b-1", "status": "installed"},
        {"name": "alpha-backend", "canister_id": "be-1", "status": "installed"},
        {"name": "alpha-frontend", "canister_id": "fe-1", "status": "installed"},
    ])
    ready, missing = stand_readiness(tree, "alpha", stand_required_members("alpha"))
    assert missing == []
    assert ready["alpha-backend"] == "be-1"
    assert ready["alpha-frontend"] == "fe-1"


def test_token_is_not_a_required_stand_member():
    canisters = [
        {"name": "alpha-backend", "canister_id": "be-1", "status": "installed"},
        {"name": "alpha-frontend", "canister_id": "fe-1", "status": "installed"},
        {"name": "alpha-token", "canister_id": "tk-1", "status": "installed"},
    ]
    ready, missing = stand_readiness(_tree("alpha", canisters), "alpha",
                                     stand_required_members("alpha"))
    assert missing == []
    assert "alpha-token" not in stand_required_members("alpha")
    assert ready["alpha-token"] == "tk-1"


def _built_tree(stand: str, built: bool, build_error: str = "") -> dict:
    tree = _tree(stand, [
        {"name": f"{stand}-backend", "canister_id": "be-1", "status": "installed"},
        {"name": f"{stand}-frontend", "canister_id": "fe-1", "status": "installed"},
    ])
    tree["sections"][1]["stands"][0]["built"] = built
    tree["sections"][1]["stands"][0]["build_error"] = build_error
    return tree


def test_installed_wasm_is_not_ready_while_assets_are_still_uploading():
    gate, detail = stand_build_gate(_built_tree("alpha", built=False), "alpha")
    assert gate == "waiting"
    assert "uploading" in detail


def test_build_error_fails_the_stand():
    gate, detail = stand_build_gate(
        _built_tree("alpha", built=False, build_error="not built after 12 rounds"),
        "alpha",
    )
    assert gate == "failed"
    assert detail == "not built after 12 rounds"


def test_built_stand_with_no_error_is_ready():
    gate, detail = stand_build_gate(_built_tree("alpha", built=True), "alpha")
    assert gate == "ready"
    assert detail == ""


def test_other_stands_and_missing_stand_are_ignored():
    tree = _tree("beta", [
        {"name": "beta-backend", "canister_id": "be-2", "status": "installed"},
    ])
    assert installed_stand_canisters(tree, "alpha") == {}
    assert installed_stand_canisters({}, "alpha") == {}
    _, missing = stand_readiness(tree, "alpha", stand_required_members("alpha"))
    assert missing == ["alpha-backend", "alpha-frontend"]
