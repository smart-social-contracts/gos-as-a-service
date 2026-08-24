"""Tests for deployment manifest access helpers."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from manifest_access import can_view_deployment_manifest  # noqa: E402


def test_controller_may_view_any_manifest():
    assert can_view_deployment_manifest(
        caller="other-principal",
        owner="owner-principal",
        is_controller=True,
    )


def test_owner_may_view_own_manifest():
    assert can_view_deployment_manifest(
        caller="owner-principal",
        owner="owner-principal",
        is_controller=False,
    )


def test_non_owner_non_controller_denied():
    assert not can_view_deployment_manifest(
        caller="other-principal",
        owner="owner-principal",
        is_controller=False,
    )
