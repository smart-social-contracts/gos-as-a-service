"""Tests for the frontend Commit-permission step.

The installer is not a controller of a realm's asset canister and holds no
ManagePermissions there (the platform provisioner and the governance multisig
are the controllers). It therefore verifies the grant Casals makes and reports
a precise failure when nobody made it — it never claims to have made it, and it
never turns an authorization refusal into something a retry could fix.
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from asset_permissions import (  # noqa: E402
    grant_frontend_access_outcome,
    grant_permission_candid,
    is_permission_denied,
    list_permitted_candid,
    missing_commit_grant_error,
    principal_in_candid_vec,
)

BACKEND = "pxip5-cyaaa-aaaae-ag3dq-cai"
FRONTEND = "o2glt-nqaaa-aaaae-ag3ea-cai"

# The live rejection from job_20260828152332_870e.
DENIAL = (
    "Rejection code 4, Caller does not have ManagePermissions permission "
    "and is not a controller"
)


def test_list_permitted_candid_asks_for_commit_holders():
    assert list_permitted_candid() == "(record { permission = variant { Commit } })"


def test_grant_permission_candid_names_the_backend():
    arg = grant_permission_candid(BACKEND)
    assert f'principal "{BACKEND}"' in arg
    assert "variant { Commit }" in arg


def test_permitted_list_is_read_from_the_decoded_response():
    decoded = f'(vec {{ principal "aaaaa-aa"; principal "{BACKEND}" }})'
    assert principal_in_candid_vec(decoded, BACKEND) is True
    assert principal_in_candid_vec(decoded, FRONTEND) is False
    assert principal_in_candid_vec("", BACKEND) is False
    assert principal_in_candid_vec(decoded, "") is False


def test_manage_permissions_rejection_is_recognised_as_a_refusal():
    assert is_permission_denied(DENIAL) is True
    assert is_permission_denied("Rejection code 2, Couldn't send message") is False
    assert is_permission_denied("") is False


def test_grant_already_made_by_casals_needs_no_installer_grant():
    status, note, error = grant_frontend_access_outcome(permitted_before=True)
    assert status == "completed"
    assert "platform provisioner" in note
    assert error == ""


def test_successful_installer_grant_completes_the_step():
    status, note, error = grant_frontend_access_outcome(
        permitted_before=False, grant_error="",
    )
    assert (status, error) == ("completed", "")
    assert "installer" in note


def test_refusal_with_the_permission_already_present_completes():
    """Casals granted Commit between the probe and the grant attempt."""
    status, _note, error = grant_frontend_access_outcome(
        permitted_before=False, grant_error=DENIAL, permitted_after=True,
    )
    assert (status, error) == ("completed", "")


def test_refusal_without_the_permission_fails_with_the_real_reason():
    status, _note, error = grant_frontend_access_outcome(
        permitted_before=False,
        grant_error=DENIAL,
        permitted_after=False,
        backend_id=BACKEND,
        frontend_id=FRONTEND,
    )
    assert status == "failed"
    assert BACKEND in error and FRONTEND in error
    assert "ManagePermissions" in error
    assert "Casals must grant" in error
    assert "Retrying this deployment cannot change the outcome" in error


def test_transient_grant_failure_is_reported_as_itself():
    status, _note, error = grant_frontend_access_outcome(
        permitted_before=False,
        grant_error="Rejection code 2, Couldn't send message",
        permitted_after=False,
    )
    assert status == "failed"
    assert error.startswith("grant_permission failed:")
    assert "Casals must grant" not in error


def test_missing_grant_error_carries_the_rejection():
    error = missing_commit_grant_error(BACKEND, FRONTEND, DENIAL)
    assert DENIAL in error
