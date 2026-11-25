"""A deployment is charged exactly once, whatever happens to it on the way (gos-as-a-service#109).

The installer settles a job's credit hold with the registry when the job ends:
release on failure, capture on success. Three defects let a realm that failed
and was then retried complete for free: the success settlement was dropped once
any settlement had been sent, the registry refused to capture a released hold,
and the installer marked a settlement done whatever the registry answered.

These run the installer on the simulated IC against the real registry credit
logic: a realm is requested (credits held), fails or not, is retried, and the
test reads where its credits ended up.
"""

import pytest

import installer_sim
from installer_sim import DEPLOYMENT_COST, FOUNDER, STARTING_CREDITS, simulate
from realm_registry_backend.api import credits
from realm_registry_backend.core import env_config, models

OWNER = f"{FOUNDER}-0"
PATH_AFTER_RETRY = ["provisioning", "failed", "provisioning", "extensions", "registering", "completed"]


def the_job(installer):
    (job,) = installer.DeploymentJob.instances()
    return job


def statuses(sim, job_id):
    return [status for _time, status in sim.history[job_id]]


def balance(principal=OWNER):
    return models.UserCredits[principal].balance


def retry_as(installer, sim, caller, results):
    """``caller`` presses Retry; the call's answer is appended to ``results``."""

    def act():
        def call():
            results.append((yield from installer.retry_deployment(the_job(installer).name)))

        sim.caller_id = caller
        sim.run(call())  # runs up to its first inter-canister call, where the caller is read
        sim.caller_id = installer_sim.REGISTRY_ID

    return act


def retry_as_owner(installer, sim, results):
    return retry_as(installer, sim, OWNER, results)


def fail(installer, reason="the stand did not build"):
    return lambda: installer._fail_job(the_job(installer), reason)


def test_a_deployment_that_succeeds_is_charged_once(installer):
    sim = simulate(installer, realms=1)

    job = the_job(installer)
    assert job.status == "completed"
    assert sim.settlements[job.name] == ["succeeded"]
    assert models.DeploymentCreditHold[job.name].status == "captured"
    assert balance() == STARTING_CREDITS - DEPLOYMENT_COST
    assert models.UserCredits[OWNER].total_spent == DEPLOYMENT_COST


def test_a_failed_deployment_is_refunded_and_says_so_in_the_history(installer):
    sim = simulate(installer, realms=1, setup=lambda sim: sim.at(5, fail(installer)))

    job = the_job(installer)
    assert job.status == "failed"
    assert sim.settlements[job.name] == ["failed"]
    assert models.DeploymentCreditHold[job.name].status == "released"
    assert balance() == STARTING_CREDITS
    kinds = [tx.transaction_type for tx in models.CreditTransaction.instances() if tx.principal_id == OWNER]
    assert sorted(kinds) == ["hold", "release", "topup"]


def test_a_retry_that_succeeds_is_charged_once(installer):
    results = []

    def failure_then_retry(sim):
        sim.at(5, fail(installer))
        sim.at(200, retry_as_owner(installer, sim, results))

    sim = simulate(installer, realms=1, setup=failure_then_retry)

    job = the_job(installer)
    assert "Ok" in results[0]
    assert statuses(sim, job.name) == PATH_AFTER_RETRY
    assert sim.settlements[job.name] == ["failed", "retried", "succeeded"]
    assert models.DeploymentCreditHold[job.name].status == "captured"
    assert balance() == STARTING_CREDITS - DEPLOYMENT_COST
    assert models.UserCredits[OWNER].total_spent == DEPLOYMENT_COST


def test_a_retry_that_fails_again_is_refunded_again(installer):
    def two_failures(sim):
        sim.at(5, fail(installer))
        sim.at(200, retry_as_owner(installer, sim, []))
        sim.at(205, fail(installer, "failed again"))

    sim = simulate(installer, realms=1, setup=two_failures)

    job = the_job(installer)
    assert job.status == "failed"
    assert sim.settlements[job.name] == ["failed", "retried", "failed"]
    assert models.DeploymentCreditHold[job.name].status == "released"
    assert balance() == STARTING_CREDITS


def test_a_retry_the_owner_cannot_pay_for_is_refused(installer):
    results = []

    def broke_before_retry(sim):
        sim.at(5, fail(installer))
        sim.at(100, lambda: credits.deduct_user_credits(OWNER, STARTING_CREDITS))
        sim.at(200, retry_as_owner(installer, sim, results))

    sim = simulate(installer, realms=1, setup=broke_before_retry)

    job = the_job(installer)
    assert "Insufficient credits" in results[0]["Err"]["message"]
    assert job.status == "failed"
    assert sim.settlements[job.name] == ["failed", "retried (refused)"]
    assert models.DeploymentCreditHold[job.name].status == "released"


def test_a_job_the_registry_never_held_retries_without_a_charge(installer):
    """A registry in can_test_mode holds nothing: there is no hold to take again, and nothing to refuse."""
    results = []

    def no_hold(sim):
        sim.at(1, lambda: env_config.apply_env_config({"can_test_mode": True}))
        sim.at(1, lambda: models.DeploymentCreditHold[the_job(installer).name].delete())
        sim.at(5, fail(installer))
        sim.at(200, retry_as_owner(installer, sim, results))

    simulate(installer, realms=1, setup=no_hold)

    assert "Ok" in results[0]
    assert the_job(installer).status == "completed"


def test_a_settlement_the_registry_refuses_is_tried_again(installer):
    """The hold is missing when the failure is settled (the registry creates it a moment late)."""

    def hold_arrives_late(sim):
        sim.at(1, lambda: models.DeploymentCreditHold[the_job(installer).name].delete())
        sim.at(5, fail(installer))
        sim.at(100, lambda: credits.create_deployment_hold(OWNER, the_job(installer).name, DEPLOYMENT_COST))

    sim = simulate(installer, realms=1, setup=hold_arrives_late)

    job = the_job(installer)
    assert sim.settlements[job.name] == ["failed (refused)", "failed (refused)", "failed"]
    assert int(job.settlement_notified) == 1
    assert models.DeploymentCreditHold[job.name].status == "released"


def test_a_registry_that_does_not_answer_is_tried_again_then_left(installer):
    def registry_down(sim):
        sim.at(4, lambda: setattr(sim, "registry_down", True))
        sim.at(5, fail(installer))

    sim = simulate(installer, realms=1, setup=registry_down, run_s=5000)

    job = the_job(installer)
    assert int(job.settlement_attempts) == installer._SETTLEMENT_MAX_ATTEMPTS
    assert int(job.settlement_notified) == 0
    assert sim.settlements == {}


def test_a_settlement_being_tried_again_survives_an_upgrade(installer):
    def upgrade_while_registry_is_down(sim):
        def upgrade():
            sim._events.clear()  # an upgrade drops the canister's timers
            sim.registry_down = False
            installer._resume_pending_settlements()

        sim.at(4, lambda: setattr(sim, "registry_down", True))
        sim.at(5, fail(installer))
        sim.at(10, upgrade)

    sim = simulate(installer, realms=1, setup=upgrade_while_registry_is_down)

    job = the_job(installer)
    assert sim.settlements[job.name] == ["failed"]
    assert int(job.settlement_notified) == 1
    assert models.DeploymentCreditHold[job.name].status == "released"


def test_a_retry_waits_for_the_failure_to_be_settled(installer):
    """Taking the hold again before the refund arrived would let the refund release the retry's hold."""
    results = []

    def retry_too_early(sim):
        sim.at(4, lambda: setattr(sim, "registry_down", True))
        sim.at(5, fail(installer))
        sim.at(20, retry_as_owner(installer, sim, results))

    simulate(installer, realms=1, setup=retry_too_early, run_s=30)

    assert "still being settled" in results[0]["Err"]["message"]
    assert the_job(installer).status == "failed"


def test_only_the_owner_or_a_controller_retries(installer):
    results = []

    def stranger_retries(sim):
        sim.at(5, fail(installer))
        sim.at(20, retry_as(installer, sim, "someone-else", results))

    simulate(installer, realms=1, setup=stranger_retries, run_s=30)

    assert "unauthorized" in results[0]["Err"]["message"]
    assert the_job(installer).status == "failed"
