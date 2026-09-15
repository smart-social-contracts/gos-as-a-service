"""Tests for the "wait until the conductor installed the stand" readiness helper."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from stand_readiness import (
    installed_stand_canisters,
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


def test_required_members_include_token_only_when_requested():
    assert stand_required_members("alpha", with_token=False) == ["alpha-backend", "alpha-frontend"]
    assert stand_required_members("alpha", with_token=True) == [
        "alpha-backend", "alpha-frontend", "alpha-token",
    ]


def test_created_but_not_installed_is_not_ready():
    tree = _tree("alpha", [
        {"name": "alpha-baton", "canister_id": "b-1", "status": "installed"},
        {"name": "alpha-backend", "canister_id": "be-1", "status": "created"},
        {"name": "alpha-frontend", "canister_id": "", "status": "pending"},
    ])
    ready, missing = stand_readiness(tree, "alpha", stand_required_members("alpha", with_token=False))
    assert ready == {"alpha-baton": "b-1"}
    assert missing == ["alpha-backend", "alpha-frontend"]


def test_ready_when_every_required_member_is_installed():
    tree = _tree("alpha", [
        {"name": "alpha-baton", "canister_id": "b-1", "status": "installed"},
        {"name": "alpha-backend", "canister_id": "be-1", "status": "installed"},
        {"name": "alpha-frontend", "canister_id": "fe-1", "status": "installed"},
    ])
    ready, missing = stand_readiness(tree, "alpha", stand_required_members("alpha", with_token=False))
    assert missing == []
    assert ready["alpha-backend"] == "be-1"
    assert ready["alpha-frontend"] == "fe-1"


def test_token_member_gates_readiness_when_requested():
    canisters = [
        {"name": "alpha-backend", "canister_id": "be-1", "status": "installed"},
        {"name": "alpha-frontend", "canister_id": "fe-1", "status": "installed"},
    ]
    _, missing = stand_readiness(_tree("alpha", canisters), "alpha",
                                 stand_required_members("alpha", with_token=True))
    assert missing == ["alpha-token"]
    canisters.append({"name": "alpha-token", "canister_id": "tk-1", "status": "installed"})
    ready, missing = stand_readiness(_tree("alpha", canisters), "alpha",
                                     stand_required_members("alpha", with_token=True))
    assert missing == []
    assert ready["alpha-token"] == "tk-1"


def test_other_stands_and_missing_stand_are_ignored():
    tree = _tree("beta", [
        {"name": "beta-backend", "canister_id": "be-2", "status": "installed"},
    ])
    assert installed_stand_canisters(tree, "alpha") == {}
    assert installed_stand_canisters({}, "alpha") == {}
    _, missing = stand_readiness(tree, "alpha", stand_required_members("alpha", with_token=False))
    assert missing == ["alpha-backend", "alpha-frontend"]
