"""Tests for the installer's caller checks."""

import ast
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from manifest_access import (  # noqa: E402
    is_registry_or_controller,
    can_report_on_job,
    can_view_deployment_manifest,
    names_only_own_canisters,
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
    return is_registry_or_controller(
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


def _may_report(caller, casals=CASALS, is_controller=False):
    return can_report_on_job(
        caller=caller, casals_principal=casals, is_controller=is_controller
    )


def test_casals_and_controller_may_report_on_a_job():
    assert _may_report(CASALS)
    assert _may_report("a-controller", is_controller=True)


def test_other_callers_may_not_report_on_a_job():
    assert not _may_report("job-owner")
    assert not _may_report(ANONYMOUS)
    assert not _may_report(REGISTRY)


def test_nobody_but_a_controller_reports_while_casals_is_unset():
    assert not _may_report(ANONYMOUS, casals="")
    assert not _may_report("", casals="")
    assert _may_report("a-controller", casals="", is_controller=True)


def _endpoint_source(name: str) -> str:
    with open(os.path.join(_REPO_ROOT, "src/realm_installer/main.py"), encoding="utf-8") as fh:
        src = fh.read()
    return src.split(f"def {name}(", 1)[1].split("\n@", 1)[0]


def test_every_guarded_endpoint_checks_the_caller():
    for name in ("report_deployment_failure", "report_canister_ready",
                 "report_frontend_verified", "take_pre_upgrade_snapshot"):
        assert "_caller_may_report()" in _endpoint_source(name), name
    for name in ("enqueue_deployment", "cancel_deployment"):
        assert "_caller_is_registry_or_controller()" in _endpoint_source(name), name
    assert "ic.is_controller(ic.caller())" in _endpoint_source("get_pending_deployments")


def test_a_new_deployment_may_name_no_canisters():
    assert names_only_own_canisters(named_ids={}, own_canister_ids=set())
    assert names_only_own_canisters(named_ids=None, own_canister_ids=set())
    assert names_only_own_canisters(named_ids={"backend": "", "frontend": " "}, own_canister_ids=set())


def test_a_foreign_backend_is_refused():
    assert not names_only_own_canisters(
        named_ids={"backend": "victim-backend"}, own_canister_ids={"my-backend", "my-frontend"},
    )


def test_a_foreign_frontend_is_refused_even_with_an_own_backend():
    assert not names_only_own_canisters(
        named_ids={"backend": "my-backend", "frontend": "victim-frontend"},
        own_canister_ids={"my-backend", "my-frontend"},
    )


def test_an_upgrade_of_the_requesters_own_realm_is_allowed():
    assert names_only_own_canisters(
        named_ids={"backend": "my-backend", "frontend": "my-frontend"},
        own_canister_ids={"my-backend", "my-frontend"},
    )


def test_enqueue_checks_named_canisters_unless_a_controller_files_the_job():
    source = _endpoint_source("enqueue_deployment")
    assert "names_only_own_canisters(" in source
    assert "not ic.is_controller(ic.caller())" in source


def test_a_job_whose_extension_task_could_not_be_created_is_failed_not_registered():
    with open(os.path.join(_REPO_ROOT, "src/realm_installer/main.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_start_extensions_for_job")
    handler = next(n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler))
    called = {n.func.id for n in ast.walk(handler) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_fail_job" in called
    assert "schedule_registration" not in called
