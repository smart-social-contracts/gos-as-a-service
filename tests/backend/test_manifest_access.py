"""Tests for the installer's caller checks."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from manifest_access import (  # noqa: E402
    can_enqueue_deployment,
    can_report_on_job,
    can_view_deployment_manifest,
)


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


REGISTRY = "registry-principal"
CASALS = "casals-principal"
ANONYMOUS = "2vxsx-fae"


def _may_enqueue(caller, registry=REGISTRY, is_controller=False):
    return can_enqueue_deployment(
        caller=caller, registry_principal=registry, is_controller=is_controller
    )


def test_registry_and_controller_may_enqueue():
    assert _may_enqueue(REGISTRY)
    assert _may_enqueue("a-controller", is_controller=True)


def test_other_callers_may_not_enqueue():
    assert not _may_enqueue("some-user")
    assert not _may_enqueue(ANONYMOUS)


def test_nobody_but_a_controller_enqueues_while_no_registry_is_configured():
    assert not _may_enqueue(ANONYMOUS, registry="")
    assert not _may_enqueue("", registry="")
    assert _may_enqueue("a-controller", registry="", is_controller=True)


def _may_report(caller, owner="owner-principal", casals=CASALS, is_controller=False):
    return can_report_on_job(
        caller=caller, owner=owner, casals_principal=casals, is_controller=is_controller
    )


def test_owner_casals_and_controller_may_report_on_a_job():
    assert _may_report("owner-principal")
    assert _may_report(CASALS)
    assert _may_report("a-controller", is_controller=True)


def test_other_callers_may_not_report_on_a_job():
    assert not _may_report("some-other-user")
    assert not _may_report(ANONYMOUS)
    assert not _may_report(REGISTRY)


def test_nobody_but_the_owner_or_a_controller_reports_while_casals_is_unset():
    assert not _may_report(ANONYMOUS, casals="")
    assert not _may_report("", casals="")
    assert _may_report("owner-principal", casals="")


def test_a_job_without_an_owner_is_not_open_to_the_anonymous_caller():
    assert not _may_report(ANONYMOUS, owner="")


def _endpoint_source(name: str) -> str:
    with open(os.path.join(_REPO_ROOT, "src/realm_installer/main.py"), encoding="utf-8") as fh:
        src = fh.read()
    return src.split(f"def {name}(", 1)[1].split("\n@", 1)[0]


def test_every_guarded_endpoint_checks_the_caller():
    for name in ("report_deployment_failure", "report_canister_ready",
                 "report_frontend_verified", "take_pre_upgrade_snapshot"):
        assert "_caller_may_report_on(job)" in _endpoint_source(name), name
    assert "can_enqueue_deployment(" in _endpoint_source("enqueue_deployment")
    assert "ic.is_controller(ic.caller())" in _endpoint_source("get_pending_deployments")
