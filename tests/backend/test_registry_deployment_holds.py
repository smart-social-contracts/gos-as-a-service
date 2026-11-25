"""The registry's credit hold for a deployment: held, captured or released, and held again on a retry."""

import pytest

from realm_registry_backend.api.credits import (
    add_user_credits,
    capture_deployment_hold,
    create_deployment_hold,
    release_deployment_hold,
    retake_deployment_hold,
)
from realm_registry_backend.core.env_config import apply_env_config, settle_deployment_retried
from realm_registry_backend.core.models import CreditTransaction, DeploymentCreditHold, UserCredits

OWNER = "owner-principal"
INSTALLER = "installer-principal"
JOB = "job-1"


@pytest.fixture(autouse=True)
def _clean_credits():
    for entity in (CreditTransaction, DeploymentCreditHold, UserCredits):
        for row in list(entity.instances()):
            row.delete()
    apply_env_config({"installer_id": INSTALLER, "can_test_mode": False})
    add_user_credits(OWNER, 20)
    create_deployment_hold(OWNER, JOB, 5, "Realm deployment")


def balance():
    return UserCredits[OWNER].balance


def kinds():
    return sorted(tx.transaction_type for tx in CreditTransaction.instances() if tx.principal_id == OWNER)


def test_releasing_a_hold_writes_its_transaction():
    assert release_deployment_hold(JOB, "Failed: boom")["success"]

    assert balance() == 20
    assert kinds() == ["hold", "release", "topup"]
    release = next(tx for tx in CreditTransaction.instances() if tx.transaction_type == "release")
    assert release.amount == 5
    assert JOB in release.description


def test_a_released_hold_is_taken_again_and_then_captured():
    release_deployment_hold(JOB)

    assert retake_deployment_hold(JOB)["success"]
    assert DeploymentCreditHold[JOB].status == "held"
    assert balance() == 15
    assert kinds() == ["hold", "hold", "release", "topup"]

    assert capture_deployment_hold(JOB)["success"]
    assert UserCredits[OWNER].total_spent == 5
    assert balance() == 15


def test_taking_a_held_hold_again_changes_nothing():
    out = retake_deployment_hold(JOB)

    assert out["success"] and out["idempotent"]
    assert balance() == 15
    assert kinds() == ["hold", "topup"]


def test_a_captured_hold_cannot_be_taken_again():
    capture_deployment_hold(JOB)

    out = retake_deployment_hold(JOB)

    assert out["success"] is False
    assert "captured" in out["error"]


def test_a_hold_is_not_taken_again_when_the_balance_is_short():
    release_deployment_hold(JOB)
    UserCredits[OWNER].balance = 4

    out = retake_deployment_hold(JOB)

    assert out["success"] is False
    assert "Insufficient credits" in out["error"]
    assert DeploymentCreditHold[JOB].status == "released"
    assert balance() == 4


def test_only_the_installer_reports_a_retry():
    release_deployment_hold(JOB)

    assert settle_deployment_retried(JOB, "someone-else")["success"] is False
    assert DeploymentCreditHold[JOB].status == "released"

    out = settle_deployment_retried(JOB, INSTALLER)
    assert out == {"success": True, "job_id": JOB, "settlement": "held"}
    assert DeploymentCreditHold[JOB].status == "held"


def test_a_retry_of_a_job_that_was_never_held_has_nothing_to_take():
    out = settle_deployment_retried("job-without-hold", INSTALLER)

    assert out == {"success": True, "job_id": "job-without-hold", "settlement": "no_hold"}
