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
    canisters_of_other_requesters,
    canisters_of_requester,
    names_only_own_canisters,
)
from stand_create_args import stand_for_new_job  # noqa: E402


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
    assert "not caller_is_controller and not names_only_own_canisters(" in source
    assert "caller_is_controller = ic.is_controller(ic.caller())" in source


def test_a_job_whose_extension_task_could_not_be_created_is_failed_not_registered():
    with open(os.path.join(_REPO_ROOT, "src/realm_installer/main.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_start_extensions_for_job")
    handler = next(n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler))
    called = {n.func.id for n in ast.walk(handler) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_fail_job" in called
    assert "schedule_registration" not in called


class _Job:
    def __init__(self, caller, backend, frontend):
        self.caller_principal = caller
        self.backend_canister_id = backend
        self.frontend_canister_id = frontend


VICTIM_JOB = _Job("victim", "victim-backend", "victim-frontend")


def test_a_realm_backend_upgrading_itself_owns_its_own_pair():
    jobs = [VICTIM_JOB, _Job("someone-else", "other-backend", "other-frontend")]
    own = canisters_of_requester(jobs, "victim-backend")
    assert names_only_own_canisters(
        named_ids={"backend": "victim-backend", "frontend": "victim-frontend"}, own_canister_ids=own,
    )


def test_a_canister_cannot_pair_itself_with_a_foreign_frontend():
    own = canisters_of_requester([VICTIM_JOB], "attacker-canister")
    assert not names_only_own_canisters(
        named_ids={"backend": "attacker-canister", "frontend": "victim-frontend"}, own_canister_ids=own,
    )


def test_canisters_of_other_requesters_excludes_the_requesters_own_jobs():
    jobs = [VICTIM_JOB, _Job("attacker", "attacker-backend", "attacker-frontend")]
    assert canisters_of_other_requesters(jobs, "attacker") == {"victim-backend", "victim-frontend"}
    assert canisters_of_other_requesters(jobs, "victim") == {"attacker-backend", "attacker-frontend"}


def test_a_stand_of_another_requesters_job_is_detected():
    """What the provisioning pass checks before it records a stand's ids on its job."""
    jobs = [VICTIM_JOB, _Job("attacker", "", "")]
    stand_ids = {"victim-backend", "victim-frontend"}
    assert stand_ids & canisters_of_other_requesters(jobs, "attacker")
    assert not stand_ids & canisters_of_other_requesters(jobs, "victim")


def test_provisioning_fails_the_job_before_recording_ids_of_a_foreign_stand():
    with open(os.path.join(_REPO_ROOT, "src/realm_installer/main.py"), encoding="utf-8") as fh:
        body = fh.read().split("def _provision_via_casals_body", 1)[1].split("def _provision_ok_for_job", 1)[0]
    check = body.index("canisters_of_other_requesters(")
    assert check < body.index("_fail_job(job,") < body.index("job.backend_canister_id = backend_id")
    assert "return _provision_ok_for_job(job_id, job)" in body[check:body.index("job.backend_canister_id = backend_id")]


def test_a_new_job_gets_its_own_stand_whatever_the_manifest_says():
    kwargs = dict(requested="victim-realm", realm_slug="victim-realm", enqueuer_is_controller=False)
    first = stand_for_new_job(job_id="job_20261031120000_ab12", **kwargs)
    second = stand_for_new_job(job_id="job_20261031120001_ab12", **kwargs)
    assert first != "victim-realm" and first != second
    assert first.startswith("victim-realm-")


def test_a_controller_may_name_the_stand():
    assert stand_for_new_job(
        requested="platform", realm_slug="x", job_id="job_1_ab12", enqueuer_is_controller=True,
    ) == "platform"
    assert stand_for_new_job(
        requested="", realm_slug="x", job_id="job_1_ab12", enqueuer_is_controller=True,
    ) == "x-1-ab12"


def test_enqueue_stores_the_chosen_stand_so_every_later_pass_finds_it():
    source = _endpoint_source("enqueue_deployment")
    stored = source.index("manifest_json = json.dumps(manifest")
    assert source.index("stand_for_new_job(") < stored < source.index("manifest_json=manifest_json[:8190]")
