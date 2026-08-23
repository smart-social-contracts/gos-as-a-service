"""Tests for deployment phases."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gaas.descriptor import Descriptor, MultisigConfig, PlatformConfig, ServicesConfig
from gaas.known import KNOWN_CANISTER_NAMES
from gaas.phases import (
    PHASES,
    DeployContext,
    _installer_config_json,
    _casals_settings_json,
    _infra_canister_names,
    _opt_text_init_arg,
    _registry_config_json,
    _registry_runtime_config_json,
    phase_configure_backends,
    phase_controller_topology,
    phase_create_canisters,
    phase_destroy_except_frontend,
    phase_domain_wiring,
    phase_grant_commanders,
    phase_install_backends,
    phase_install_frontends,
    phase_seed_conductor,
    phase_seed_file_registry,
    run_phases,
)
from gaas.gaas_env import build_gaas_env
from gaas.dfx import detect_install_mode, _parse_candid_string
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID


def test_phases_order() -> None:
    ids = [phase_id for phase_id, _title, _func in PHASES]
    assert ids == [
        "destroy_except_frontend",
        "validate",
        "create_canisters",
        "install_backends",
        "configure_backends",
        "seed_file_registry",
        "seed_conductor",
        "prime_cycles_snapshot",
        "configure_multisig",
        "install_frontends",
        "domain_wiring",
        "smoke_checks",
        "grant_commanders",
        "controller_topology",
    ]


@patch("gaas.phases.destroy_except_frontend")
def test_phase_destroy_except_frontend_noop_when_flag_false(mock_destroy: MagicMock) -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    ctx = DeployContext(identity="deployer", network="ic", destroy_except_frontend=False)
    phase_destroy_except_frontend(desc, ctx)
    mock_destroy.assert_not_called()


@patch("gaas.phases._save_descriptor")
@patch("gaas.phases.destroy_except_frontend")
def test_phase_destroy_except_frontend_runs_and_saves(
    mock_destroy: MagicMock,
    mock_save: MagicMock,
    tmp_path: Path,
) -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    path = tmp_path / "env.json"
    desc.save(path)
    ctx = DeployContext(
        identity="deployer",
        network="ic",
        yes=True,
        destroy_except_frontend=True,
        descriptor_path=path,
    )
    mock_destroy.return_value = {
        "cycles_reclaimed": 100,
        "cycles_evacuated": 200,
        "preserved_frontend_ids": [VALID_CANISTER_ID],
    }
    phase_destroy_except_frontend(desc, ctx)
    mock_destroy.assert_called_once()
    mock_save.assert_called_once()
    assert ctx.cycles_evacuated == 200


@patch("gaas.phases.seed_codex_catalog")
@patch("gaas.phases.ensure_version_catalog_entry", return_value="skipped")
@patch("gaas.phases.namespace_published", return_value=True)
@patch("gaas.phases.fetch_namespace_hashes")
def test_phase_seed_file_registry_skips_undeclared_catalog(
    mock_hashes: MagicMock,
    _mock_published: MagicMock,
    _mock_version_catalog: MagicMock,
    mock_seed_catalog: MagicMock,
    tmp_path: Path,
) -> None:
    mock_hashes.return_value = {"monad_backend.wasm.gz": "abc"}

    data = dict(SAMPLE_DESCRIPTOR)
    data["gos"] = [
        {
            "implementation": "monad-gos",
            "version": "v0.1.0",
            "release_repo": "smart-social-contracts/monad-gos",
            "artifacts": {
                "backend_wasm_key": "monad-backend",
                "frontend_wasm_key": "monad-assets",
            },
            "loader_profile": "monad-iframe-v1",
        }
    ]
    data["canisters"] = {
        "file_registry": VALID_CANISTER_ID,
        "realm_registry_backend": VALID_CANISTER_ID,
    }
    descriptor = Descriptor.model_validate(data)
    ctx = DeployContext(
        identity="deployer",
        network="local",
        work_dir=tmp_path / "work",
        yes=True,
    )

    phase_seed_file_registry(descriptor, ctx)

    mock_seed_catalog.assert_not_called()


@patch("gaas.phases.run_preflight")
def test_run_phases_validate_failure(mock_preflight) -> None:
    from gaas.preflight import PreflightCheck, PreflightReport

    mock_preflight.return_value = PreflightReport(
        identity="default",
        network="ic",
        checks=[PreflightCheck("identity_exists", False, "missing")],
    )

    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    ctx = DeployContext(identity="default", network="ic")

    with pytest.raises(RuntimeError, match="preflight failed"):
        run_phases(desc, ctx)

    assert ctx.completed_phases == ["destroy_except_frontend"]


@patch("gaas.phases.dfx.top_up_canister")
@patch("gaas.phases.dfx.create_canister_via_ledger")
@patch("gaas.phases.dfx.create_canister")
@patch("gaas.phases.dfx.canister_status")
@patch("gaas.phases.dfx.get_principal")
@patch("gaas.phases.dfx.use_identity")
@patch("gaas.phases.run_preflight")
def test_create_canisters_adopt_vs_create(
    mock_preflight,
    _use_identity,
    mock_principal,
    mock_status,
    mock_create,
    mock_ledger_create,
    _mock_top_up,
    tmp_path: Path,
) -> None:
    from gaas.preflight import PreflightCheck, PreflightReport

    mock_preflight.return_value = PreflightReport(
        identity="deployer",
        network="ic",
        checks=[PreflightCheck("identity_exists", True, "ok")],
    )
    mock_principal.return_value = "aaaaa-aa"
    mock_status.return_value = MagicMock(
        status="running",
        controllers=("aaaaa-aa",),
        raw="status: running",
    )
    mock_create.side_effect = [
        "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
        "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
        "ccccc-ccccc-ccccc-ccccc-ccccc-ccc",
        "ddddd-ddddd-ddddd-ddddd-ddddd-ddd",
        "fffff-fffff-fffff-fffff-fffff-fff",
        "ggggg-ggggg-ggggg-ggggg-ggggg-ggg",
        "hhhhh-hhhhh-hhhhh-hhhhh-hhhhh-hhh",
    ]
    mock_ledger_create.side_effect = [
        "eeeee-eeeee-eeeee-eeeee-eeeee-eee",
        "iiiii-iiiii-iiiii-iiiii-iiiii-iii",
        "jjjjj-jjjjj-jjjjj-jjjjj-jjjjj-jjj",
    ]

    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"realm_registry_backend": VALID_CANISTER_ID}
    desc = Descriptor.model_validate(data)
    path = tmp_path / "env.gaas.json"
    desc.save(path)

    ctx = DeployContext(
        identity="deployer",
        network="ic",
        descriptor_path=path,
    )
    phase_create_canisters(desc, ctx)

    mock_create.assert_called()
    assert desc.canisters["realm_registry_backend"] == VALID_CANISTER_ID
    # 1 adopted + 8 platform created; DNS-mapped marketplace_frontend is skipped.
    assert len(desc.canisters) == 9
    assert "marketplace_backend" in desc.canisters
    assert "file_registry" in desc.canisters
    assert "file_registry_frontend" in desc.canisters
    assert "marketplace_frontend" not in desc.canisters


@patch("gaas.phases.dfx.top_up_canister")
@patch("gaas.phases.dfx.create_canister_via_ledger")
@patch("gaas.phases.dfx.create_canister")
@patch("gaas.phases.dfx.canister_status")
@patch("gaas.phases.dfx.get_principal")
@patch("gaas.phases.dfx.use_identity")
@patch("gaas.phases.run_preflight")
def test_phase_create_canisters_restores_evacuated_cycles(
    mock_preflight,
    _use_identity,
    mock_principal,
    mock_status,
    mock_create,
    _mock_ledger_create,
    mock_top_up,
    tmp_path: Path,
) -> None:
    from gaas.preflight import PreflightCheck, PreflightReport

    mock_preflight.return_value = PreflightReport(
        identity="deployer",
        network="ic",
        checks=[PreflightCheck("identity_exists", True, "ok")],
    )
    mock_principal.return_value = "aaaaa-aa"
    mock_status.return_value = MagicMock(
        status="running",
        controllers=("aaaaa-aa",),
        raw="status: running",
    )
    casals_id = "qthgp-3yaaa-aaaae-agveq-cai"

    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {name: VALID_CANISTER_ID for name in KNOWN_CANISTER_NAMES}
    data["canisters"]["casals_backend"] = casals_id
    desc = Descriptor.model_validate(data)
    path = tmp_path / "env.gaas.json"
    desc.save(path)

    ctx = DeployContext(
        identity="deployer",
        network="ic",
        descriptor_path=path,
        cycles_evacuated=500_000_000_000,
    )
    phase_create_canisters(desc, ctx)

    mock_top_up.assert_called_once_with(
        casals_id,
        500_000_000_000,
        "ic",
        identity="deployer",
    )


@patch("gaas.phases.dfx.top_up_canister")
@patch("gaas.phases.dfx.create_canister_via_ledger")
@patch("gaas.phases.dfx.create_canister")
@patch("gaas.phases.dfx.canister_status")
@patch("gaas.phases.dfx.get_principal")
@patch("gaas.phases.dfx.use_identity")
@patch("gaas.phases.run_preflight")
def test_phase_create_canisters_skips_treasury_restore_when_zero(
    mock_preflight,
    _use_identity,
    mock_principal,
    mock_status,
    mock_create,
    _mock_ledger_create,
    mock_top_up,
    tmp_path: Path,
) -> None:
    from gaas.preflight import PreflightCheck, PreflightReport

    mock_preflight.return_value = PreflightReport(
        identity="deployer",
        network="ic",
        checks=[PreflightCheck("identity_exists", True, "ok")],
    )
    mock_principal.return_value = "aaaaa-aa"
    mock_status.return_value = MagicMock(
        status="running",
        controllers=("aaaaa-aa",),
        raw="status: running",
    )

    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {name: VALID_CANISTER_ID for name in KNOWN_CANISTER_NAMES}
    data["canisters"]["casals_backend"] = "qthgp-3yaaa-aaaae-agveq-cai"
    desc = Descriptor.model_validate(data)
    path = tmp_path / "env.gaas.json"
    desc.save(path)

    ctx = DeployContext(
        identity="deployer",
        network="ic",
        descriptor_path=path,
        cycles_evacuated=0,
    )
    phase_create_canisters(desc, ctx)

    mock_top_up.assert_not_called()


def test_registry_init_json_can_test_mode() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    default_json = json.loads(_registry_config_json(desc))
    # No billing_url in SAMPLE_DESCRIPTOR → derived can test mode, always explicit.
    assert default_json["can_test_mode"] is True
    assert default_json["portal_url"] == "https://test.gos.earth"

    open_desc = desc.model_copy(update={"flags": {"can_test_mode": True}})
    open_json = json.loads(_registry_config_json(open_desc))
    assert open_json["can_test_mode"] is True

    billed = desc.model_copy(
        update={
            "services": ServicesConfig(
                billing_url="https://billing.example.com",
                deploy_url=None,
            ),
            "flags": {"can_test_mode": True},
        }
    )
    billed_json = json.loads(_registry_config_json(billed))
    assert billed_json["can_test_mode"] is True

    # Billing present, nothing explicit → derived closed.
    billed_only = desc.model_copy(
        update={
            "services": ServicesConfig(
                billing_url="https://billing.example.com",
                deploy_url=None,
            ),
        }
    )
    assert json.loads(_registry_config_json(billed_only))["can_test_mode"] is False

    # Deprecated services.open_mode alias still honored when flags lack the key.
    alias = desc.model_copy(
        update={
            "services": ServicesConfig(
                billing_url="https://billing.example.com",
                deploy_url=None,
                open_mode=True,
            ),
        }
    )
    assert json.loads(_registry_config_json(alias))["can_test_mode"] is True

    # Deprecated flags.open_mode alias still honored when can_test_mode absent.
    legacy_flag = desc.model_copy(update={"flags": {"open_mode": True}})
    assert json.loads(_registry_config_json(legacy_flag))["can_test_mode"] is True

    # Explicit flag beats the deprecated alias.
    override = alias.model_copy(update={"flags": {"can_test_mode": False}})
    assert json.loads(_registry_config_json(override))["can_test_mode"] is False
    assert billed_json["billing_url"] == "https://billing.example.com"


def test_registry_config_json_billing_service_principal() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR).model_copy(
        update={
            "services": ServicesConfig(
                billing_url="https://billing.example.com",
                billing_service_principal="aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
            ),
        }
    )
    payload = json.loads(_registry_config_json(desc))
    assert payload["billing_service_principal"] == "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa"


def test_registry_config_json_installer_id_and_flags() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"realm_installer": VALID_CANISTER_ID}
    data["flags"] = {"can_test_mode": True}
    desc = Descriptor.model_validate(data)
    payload = json.loads(_registry_config_json(desc))
    assert payload["installer_id"] == VALID_CANISTER_ID
    assert payload["can_test_mode"] is True


def test_registry_runtime_config_json_can_test_mode() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    # No billing_url → derived can test mode.
    ic_payload = json.loads(_registry_runtime_config_json(desc, "ic"))
    assert ic_payload == {
        "test_flags": {"test_mode": True, "ii_bypass": True},
    }

    open_desc = desc.model_copy(update={"flags": {"can_test_mode": True}})
    local_payload = json.loads(_registry_runtime_config_json(open_desc, "local"))
    assert local_payload == {
        "test_flags": {"test_mode": True, "ii_bypass": True},
        "network": "local",
    }

    billed_closed = desc.model_copy(
        update={
            "services": ServicesConfig(
                billing_url="https://billing.example.com",
                deploy_url=None,
            ),
        }
    )
    assert _registry_runtime_config_json(billed_closed, "ic") is None


@patch("gaas.phases.dfx.get_principal")
@patch("gaas.phases.dfx.canister_call")
def test_phase_configure_backends_can_test_mode_sets_runtime_flags(
    mock_call: MagicMock,
    mock_principal: MagicMock,
) -> None:
    mock_principal.return_value = "deployer-principal"
    registry_id = VALID_CANISTER_ID
    installer_id = "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aab"
    casals_id = "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb"

    registry_configure_ok = json.dumps(
        {
            "success": True,
            "portal_url": "https://test.gos.earth",
            "can_test_mode": True,
        }
    ).replace("\\", "\\\\").replace('"', '\\"')

    def call_side_effect(canister_id, method, arg, network, *, identity=None, query=False):
        del network, identity, query
        if canister_id == registry_id and method == "configure":
            return f'variant {{ Ok = "{registry_configure_ok}" }}'
        if canister_id == registry_id and method == "get_env_config":
            return json.dumps({"portal_url": "https://test.gos.earth"})
        if canister_id == registry_id and method == "set_canister_config_json":
            payload = json.loads(_parse_candid_string(arg))
            assert payload["test_flags"] == {"test_mode": True, "ii_bypass": True}
            return json.dumps({"success": True})
        if canister_id == registry_id and method == "get_runtime_flags":
            return json.dumps(
                {"success": True, "test_mode": True, "test_mode_ii_bypass": True}
            )
        if canister_id == installer_id and method == "configure":
            return json.dumps({"success": True})
        if canister_id == installer_id and method == "get_installer_config":
            return json.dumps({"registry_backend_id": registry_id})
        if canister_id == casals_id and method == "set_settings":
            return json.dumps({"ok": True})
        raise AssertionError(f"unexpected call: {canister_id} {method}")

    mock_call.side_effect = call_side_effect

    data = dict(SAMPLE_DESCRIPTOR)
    data["flags"] = {"can_test_mode": True}
    data["canisters"] = {
        "realm_registry_backend": registry_id,
        "realm_installer": installer_id,
        "casals_backend": casals_id,
    }
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic")
    phase_configure_backends(desc, ctx)

    runtime_calls = [
        c
        for c in mock_call.call_args_list
        if c[0][0] == registry_id and c[0][1] == "set_canister_config_json"
    ]
    assert len(runtime_calls) == 1


@patch("gaas.phases.dfx.get_principal")
@patch("gaas.phases.dfx.canister_call")
def test_phase_configure_backends_closed_skips_runtime_flags(
    mock_call: MagicMock,
    mock_principal: MagicMock,
) -> None:
    mock_principal.return_value = "deployer-principal"
    registry_id = VALID_CANISTER_ID
    installer_id = "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aab"
    casals_id = "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb"

    registry_configure_ok = json.dumps(
        {
            "success": True,
            "portal_url": "https://test.gos.earth",
            "can_test_mode": False,
        }
    ).replace("\\", "\\\\").replace('"', '\\"')

    def call_side_effect(canister_id, method, arg, network, *, identity=None, query=False):
        del arg, network, identity, query
        if canister_id == registry_id and method == "configure":
            return f'variant {{ Ok = "{registry_configure_ok}" }}'
        if canister_id == registry_id and method == "get_env_config":
            return json.dumps({"portal_url": "https://test.gos.earth"})
        if canister_id == installer_id and method == "configure":
            return json.dumps({"success": True})
        if canister_id == installer_id and method == "get_installer_config":
            return json.dumps({"registry_backend_id": registry_id})
        if canister_id == casals_id and method == "set_settings":
            return json.dumps({"ok": True})
        raise AssertionError(f"unexpected call: {canister_id} {method}")

    mock_call.side_effect = call_side_effect

    data = dict(SAMPLE_DESCRIPTOR)
    data["services"] = ServicesConfig(
        billing_url="https://billing.example.com",
        deploy_url=None,
    )
    data["canisters"] = {
        "realm_registry_backend": registry_id,
        "realm_installer": installer_id,
        "casals_backend": casals_id,
    }
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic")
    phase_configure_backends(desc, ctx)

    runtime_calls = [
        c
        for c in mock_call.call_args_list
        if c[0][1] == "set_canister_config_json"
    ]
    assert runtime_calls == []


def test_installer_config_json_includes_ids() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "realm_registry_backend": VALID_CANISTER_ID,
        "file_registry": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aab",
        "marketplace_backend": "ccccc-ccccc-ccccc-ccccc-ccccc-ccc",
        "casals_backend": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
    }
    desc = Descriptor.model_validate(data)
    payload = json.loads(_installer_config_json(desc))
    assert payload["registry_backend_id"] == VALID_CANISTER_ID
    assert payload["file_registry_id"] == "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aab"
    assert payload["marketplace_id"] == "ccccc-ccccc-ccccc-ccccc-ccccc-ccc"
    assert payload["casals_canister_id"] == "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb"
    assert payload["portal_url"] == "https://test.gos.earth"
    assert payload["provision_via_casals"] is True
    assert payload["create_stand_baton"] is True
    assert payload["baton_wasm_key"] == "orchestration-baton@1.3.0"
    assert payload["cycle_threshold_cycles"] == 2_000_000_000_000


def test_installer_config_json_casals_backend_key() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"casals_backend": VALID_CANISTER_ID}
    desc = Descriptor.model_validate(data)
    payload = json.loads(_installer_config_json(desc))
    assert payload["casals_canister_id"] == VALID_CANISTER_ID


def test_casals_settings_json_prefers_casals_file_registry() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "file_registry": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
        "casals_file_registry": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
    }
    desc = Descriptor.model_validate(data)
    payload = json.loads(_casals_settings_json(desc, "deployer-principal"))
    assert payload["file_registry_canister_id"] == "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb"


def test_casals_settings_json_defaults_and_test_mode() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "file_registry": VALID_CANISTER_ID,
        "file_registry_frontend": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aab",
        "casals_frontend": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
        "realm_installer": "ccccc-ccccc-ccccc-ccccc-ccccc-ccc",
    }
    desc = Descriptor.model_validate(data)
    billed = desc.model_copy(
        update={
            "services": ServicesConfig(
                billing_url="https://billing.example.com",
            ),
            "flags": {},
        }
    )
    closed = json.loads(_casals_settings_json(billed, "deployer-principal"))
    assert closed["monitor_enabled"] is False
    assert closed["default_min_cycles"] == 2_000_000_000_000
    assert closed["default_topup_cycles"] == 2_000_000_000_000
    assert closed["treasury_reserve"] == 2_000_000_000_000
    assert closed["create_cycles"] == 2_000_000_000_000
    assert "extra_controller_principals" not in closed

    open_desc = desc.model_copy(update={"flags": {"can_test_mode": True}})
    open_payload = json.loads(_casals_settings_json(open_desc, "deployer-principal"))
    assert open_payload["extra_controller_principals"] == ["deployer-principal"]


def test_casals_settings_json_monitor_url() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"file_registry": VALID_CANISTER_ID}
    data["services"] = {"monitor_url": "https://monitor.example.com"}
    desc = Descriptor.model_validate(data)
    payload = json.loads(_casals_settings_json(desc, "deployer-principal"))
    assert payload["monitor_enabled"] is True
    assert payload["monitor_service_url"] == "https://monitor.example.com"
    assert "monitor_principal" not in payload


def test_casals_settings_json_monitor_url_and_principal() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"file_registry": VALID_CANISTER_ID}
    data["services"] = {
        "monitor_url": "https://monitor.example.com",
        "monitor_principal": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
    }
    desc = Descriptor.model_validate(data)
    payload = json.loads(_casals_settings_json(desc, "deployer-principal"))
    assert payload["monitor_enabled"] is True
    assert payload["monitor_service_url"] == "https://monitor.example.com"
    assert payload["monitor_principal"] == "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa"


def test_casals_settings_json_monitor_principal_without_url() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"file_registry": VALID_CANISTER_ID}
    data["services"] = {"monitor_principal": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa"}
    desc = Descriptor.model_validate(data)
    payload = json.loads(_casals_settings_json(desc, "deployer-principal"))
    assert payload["monitor_enabled"] is False
    assert "monitor_service_url" not in payload
    assert payload["monitor_principal"] == "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa"


def test_casals_settings_json_no_monitor_url() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"file_registry": VALID_CANISTER_ID}
    desc = Descriptor.model_validate(data)
    payload = json.loads(_casals_settings_json(desc, "deployer-principal"))
    assert payload["monitor_enabled"] is False
    assert "monitor_service_url" not in payload
    assert "monitor_principal" not in payload


def test_infra_canister_names() -> None:
    names = _infra_canister_names()
    assert "realm_registry_backend" in names
    assert "realm_registry_frontend" in names
    assert "realm_installer" in names
    assert "file_registry" in names
    assert "file_registry_frontend" in names
    assert "casals_backend" not in names


@patch("gaas.phases.dfx.canister_status")
@patch("gaas.phases.dfx.update_canister_settings")
@patch("gaas.phases.dfx.get_principal")
def test_controller_topology_test_mode(
    mock_principal,
    mock_update,
    mock_status,
) -> None:
    mock_principal.return_value = "deployer-principal"
    multisig_id = "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aac"
    casals_backend_id = "eeeee-eeeee-eeeee-eeeee-eeeee-eee"

    def status_side_effect(canister_id, network, *, identity=None):
        if canister_id in (casals_backend_id, "fffff-fffff-fffff-fffff-fffff-fff"):
            controllers = (multisig_id, "deployer-principal")
        else:
            controllers = (casals_backend_id, "deployer-principal")
        return MagicMock(status="running", controllers=controllers)

    mock_status.side_effect = status_side_effect
    data = dict(SAMPLE_DESCRIPTOR)
    data["flags"] = {"can_test_mode": True}
    data["canisters"] = {
        "realm_registry_backend": VALID_CANISTER_ID,
        "realm_registry_frontend": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aab",
        "realm_installer": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
        "file_registry": "ccccc-ccccc-ccccc-ccccc-ccccc-ccc",
        "file_registry_frontend": "ddddd-ddddd-ddddd-ddddd-ddddd-ddd",
        "casals_backend": "eeeee-eeeee-eeeee-eeeee-eeeee-eee",
        "casals_frontend": "fffff-fffff-fffff-fffff-fffff-fff",
        "casals_file_registry": "ggggg-ggggg-ggggg-ggggg-ggggg-ggg",
        "marketplace_backend": "hhhhh-hhhhh-hhhhh-hhhhh-hhhhh-hhh",
    }
    data["multisig"] = {"backend_id": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aac"}
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic")
    phase_controller_topology(desc, ctx)
    # casals pair + 5 infra (registry/installer/file_registry pair) +
    # casals_file_registry + marketplace_backend
    assert mock_update.call_count == 9
    first_call = mock_update.call_args_list[0]
    assert first_call[0][1] == ["aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aac", "deployer-principal"]



def test_opt_text_init_arg() -> None:
    assert _opt_text_init_arg("") == "(null)"
    assert _opt_text_init_arg('{"a": 1}') == '(opt "{\\"a\\": 1}")'


@patch("gaas.dfx.canister_status")
def test_detect_install_mode_install_when_empty(mock_status) -> None:
    mock_status.return_value = MagicMock(module_hash_missing=True)
    assert detect_install_mode(VALID_CANISTER_ID, "ic") == "install"


@patch("gaas.dfx.canister_status")
def test_detect_install_mode_upgrade_when_installed(mock_status) -> None:
    mock_status.return_value = MagicMock(module_hash_missing=False)
    assert detect_install_mode(VALID_CANISTER_ID, "ic") == "upgrade"


def test_build_gaas_env_includes_ii_origin() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"realm_registry_frontend": VALID_CANISTER_ID}
    desc = Descriptor.model_validate(data)
    env = build_gaas_env(desc, "ic")
    assert env["domain"] == "test.gos.earth"
    assert env["ii_alternative_origins"] == [f"https://{VALID_CANISTER_ID}.icp0.io"]
    assert env["canisters"]["realm_registry_frontend"]["ic"] == VALID_CANISTER_ID


@patch("gaas.phases.wait_for_dns", return_value=False)
@patch("gaas.phases.render_dns_records")
def test_domain_wiring_dns_timeout(mock_render, _wait, tmp_path: Path) -> None:
    mock_render.return_value = []
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"realm_registry_frontend": VALID_CANISTER_ID}
    desc = Descriptor.model_validate(data)
    path = tmp_path / "env.gaas.json"
    desc.save(path)
    ctx = DeployContext(
        identity="default",
        network="ic",
        descriptor_path=path,
        dns_timeout_min=1,
    )
    with pytest.raises(RuntimeError, match="DNS propagation"):
        phase_domain_wiring(desc, ctx)
    assert ctx.stopped is True


def test_parse_registry_configure_variant_ok() -> None:
    from gaas.phases import _parse_registry_configure

    raw = (
        'variant {\n    Ok = "{"success":true,"portal_url":"https://local.localhost",'
        '"billing_url":"","can_test_mode":true}"\n  }'
    )
    parsed = _parse_registry_configure(raw)
    assert parsed["success"] is True
    assert parsed["can_test_mode"] is True


@patch("gaas.phases.seed_codex_catalog")
@patch("gaas.phases.ensure_version_catalog_entry", return_value="skipped")
@patch("gaas.phases.namespace_published", return_value=False)
@patch("gaas.phases.resolve_gos_artifacts")
@patch("gaas.phases.seed_gos_entry")
@patch("gaas.phases.resolve_deploy_version")
def test_phase_seed_file_registry_gos_binaries_use_casals_file_registry(
    mock_resolve_version,
    mock_seed_gos,
    mock_resolve_artifacts,
    _mock_published,
    _mock_version_catalog,
    _mock_seed_catalog,
    tmp_path: Path,
) -> None:
    from gaas.versions import ResolvedDeployVersion

    mock_resolve_version.return_value = ResolvedDeployVersion(
        "v0.3.1", "v0.3.1", "0.3.1"
    )
    backend = tmp_path / "realm_backend.wasm.gz"
    frontend = tmp_path / "realm_frontend.tar.gz"
    backend.write_bytes(b"wasm")
    frontend.write_bytes(b"tar")
    mock_resolve_artifacts.return_value = (backend, frontend)

    realms_fr = VALID_CANISTER_ID
    casals_fr = "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aab"
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "file_registry": realms_fr,
        "casals_file_registry": casals_fr,
        "realm_registry_backend": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
    }
    descriptor = Descriptor.model_validate(data)
    ctx = DeployContext(
        identity="deployer",
        network="local",
        work_dir=tmp_path / "work",
        yes=True,
    )

    phase_seed_file_registry(descriptor, ctx)

    assert mock_seed_gos.call_args[0][0] == casals_fr


@patch("gaas.phases._http_get", return_value=(200, "ok"))
@patch("gaas.phases.dfx.canister_status")
@patch("gaas.phases.dfx.canister_call")
@patch("gaas.phases.fetch_namespace_hashes", return_value={"realm_backend.wasm.gz": "abc"})
def test_phase_smoke_checks_uses_casals_file_registry(
    mock_hashes,
    mock_call,
    mock_status,
    _mock_http,
) -> None:
    mock_status.return_value = MagicMock(status="running", controllers=())
    mock_call.return_value = json.dumps({"portal_url": "https://test.gos.earth"})

    casals_fr = "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aab"
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "realm_registry_backend": VALID_CANISTER_ID,
        "realm_registry_frontend": VALID_CANISTER_ID,
        "casals_backend": VALID_CANISTER_ID,
        "casals_frontend": VALID_CANISTER_ID,
        "file_registry": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
        "casals_file_registry": casals_fr,
    }
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="local")

    from gaas.phases import phase_smoke_checks

    phase_smoke_checks(desc, ctx)

    mock_hashes.assert_called()
    assert mock_hashes.call_args[0][0] == casals_fr


def test_platform_descriptor_optional() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    assert desc.platform is None
    with_platform = desc.model_copy(
        update={
            "platform": PlatformConfig(
                version="v0.3.1",
                release_repo="smart-social-contracts/gos-as-a-service",
            )
        }
    )
    assert with_platform.platform is not None
    assert with_platform.platform.version == "v0.3.1"


@patch("gaas.phases.ensure_section_commanders")
@patch("gaas.phases.ensure_deployments_commander")
@patch("gaas.phases.ensure_platform_stand")
@patch("gaas.phases.ensure_sheet_and_deploy_multisig")
@patch("gaas.phases.authorize_gos_entry")
@patch("gaas.phases.seed_orchestration_templates")
def test_phase_seed_conductor_registers_platform_canisters(
    _seed_templates,
    _authorize,
    _sheet,
    mock_platform_stand,
    _deployments_commander,
    _section_commanders,
) -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "realm_registry_backend": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
        "realm_registry_frontend": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
        "realm_installer": "ccccc-ccccc-ccccc-ccccc-ccccc-ccc",
        "file_registry": "ddddd-ddddd-ddddd-ddddd-ddddd-ddd",
        "file_registry_frontend": "eeeee-eeeee-eeeee-eeeee-eeeee-eee",
        "casals_backend": "fffff-fffff-fffff-fffff-fffff-fff",
        "casals_file_registry": "ggggg-ggggg-ggggg-ggggg-ggggg-ggg",
    }
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic")
    phase_seed_conductor(desc, ctx)

    mock_platform_stand.assert_called_once()
    args = mock_platform_stand.call_args[0]
    assert args[0] == "fffff-fffff-fffff-fffff-fffff-fff"
    assert args[2] == "ic"
    assert mock_platform_stand.call_args[1]["identity"] == "deployer"
    assert args[1] == [
        ("realm-registry-backend", "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa", "backend"),
        ("realm-registry-frontend", "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb", "frontend"),
        ("realm-installer", "ccccc-ccccc-ccccc-ccccc-ccccc-ccc", "backend"),
        ("file-registry", "ddddd-ddddd-ddddd-ddddd-ddddd-ddd", "backend"),
        ("file-registry-frontend", "eeeee-eeeee-eeeee-eeeee-eeeee-eee", "frontend"),
        ("casals-file-registry", "ggggg-ggggg-ggggg-ggggg-ggggg-ggg", "backend"),
    ]


PRINCIPAL_A = "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa"
PRINCIPAL_B = "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb"
CASALS_BACKEND_ID = "fffff-fffff-fffff-fffff-fffff-fff"
CASALS_FRONTEND_ID = "ggggg-ggggg-ggggg-ggggg-ggggg-ggg"
MOCK_TREE = {"sections": [{"name": "Infra"}, {"name": "Deployments"}]}


def _grant_commanders_descriptor(tmp_path: Path | None = None) -> tuple[Descriptor, DeployContext]:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "casals_backend": CASALS_BACKEND_ID,
        "casals_frontend": CASALS_FRONTEND_ID,
    }
    desc = Descriptor.model_validate(data)
    path = None
    if tmp_path is not None:
        path = tmp_path / "env.gaas.json"
        desc.save(path)
    ctx = DeployContext(
        identity="deployer",
        network="ic",
        descriptor_path=path,
    )
    return desc, ctx


@patch("gaas.phases.ensure_section_commanders")
@patch("gaas.phases.get_tree", return_value=MOCK_TREE)
@patch("gaas.phases.sys.stdin")
def test_phase_grant_commanders_non_interactive(
    mock_stdin,
    _get_tree,
    mock_ensure,
) -> None:
    mock_stdin.isatty.return_value = False
    desc, ctx = _grant_commanders_descriptor()
    ctx.yes = False

    phase_grant_commanders(desc, ctx)

    mock_ensure.assert_not_called()


@patch("gaas.phases.ensure_section_commanders")
@patch("gaas.phases.get_tree", return_value=MOCK_TREE)
@patch("gaas.phases.sys.stdin")
def test_phase_grant_commanders_non_interactive_yes_flag(
    mock_stdin,
    _get_tree,
    mock_ensure,
) -> None:
    mock_stdin.isatty.return_value = True
    desc, ctx = _grant_commanders_descriptor()
    ctx.yes = True

    phase_grant_commanders(desc, ctx)

    mock_ensure.assert_not_called()


@patch("gaas.phases._save_descriptor")
@patch("gaas.phases.console.input")
@patch("gaas.phases.ensure_section_commanders")
@patch("gaas.phases.get_tree", return_value=MOCK_TREE)
@patch("gaas.phases.sys.stdin")
def test_phase_grant_commanders_interactive_grants_and_persists(
    mock_stdin,
    _get_tree,
    mock_ensure,
    mock_input,
    mock_save,
    tmp_path: Path,
) -> None:
    mock_stdin.isatty.return_value = True
    mock_input.side_effect = [PRINCIPAL_A, PRINCIPAL_B, ""]
    desc, ctx = _grant_commanders_descriptor(tmp_path)

    phase_grant_commanders(desc, ctx)

    assert mock_ensure.call_count == 2
    for call in mock_ensure.call_args_list:
        assert call[0][0] == CASALS_BACKEND_ID
        assert call[0][1] == ["Deployments", "Infra"]
        assert len(call[0][2]) == 1
    assert mock_ensure.call_args_list[0][0][2] == [PRINCIPAL_A]
    assert mock_ensure.call_args_list[1][0][2] == [PRINCIPAL_B]
    assert desc.casals.commanders == [PRINCIPAL_A, PRINCIPAL_B]
    assert mock_save.call_count == 2


@patch("gaas.phases.console.input")
@patch("gaas.phases.ensure_section_commanders")
@patch("gaas.phases.get_tree", return_value=MOCK_TREE)
@patch("gaas.phases.sys.stdin")
def test_phase_grant_commanders_invalid_principal_reprompts(
    mock_stdin,
    _get_tree,
    mock_ensure,
    mock_input,
) -> None:
    mock_stdin.isatty.return_value = True
    mock_input.side_effect = ["not-a-principal", PRINCIPAL_A, ""]
    desc, ctx = _grant_commanders_descriptor()

    phase_grant_commanders(desc, ctx)

    mock_ensure.assert_called_once()
    assert mock_ensure.call_args[0][2] == [PRINCIPAL_A]


@patch("gaas.phases.console.input")
@patch("gaas.phases.ensure_section_commanders")
@patch("gaas.phases.get_tree", return_value=MOCK_TREE)
@patch("gaas.phases.sys.stdin")
def test_phase_grant_commanders_grant_error_continues(
    mock_stdin,
    _get_tree,
    mock_ensure,
    mock_input,
) -> None:
    mock_stdin.isatty.return_value = True
    mock_input.side_effect = [PRINCIPAL_A, PRINCIPAL_B, ""]
    mock_ensure.side_effect = [RuntimeError("grant failed"), None]
    desc, ctx = _grant_commanders_descriptor()

    phase_grant_commanders(desc, ctx)

    assert mock_ensure.call_count == 2
    assert mock_ensure.call_args_list[1][0][2] == [PRINCIPAL_B]


@patch("gaas.phases.dfx.get_principal", return_value="aaaaa-aa")
@patch("gaas.phases.dfx.deploy_assets_canister")
@patch("gaas.phases.resolve_casals_frontend_dist")
@patch("gaas.phases.frontend_dist_dir")
@patch("gaas.phases.write_gaas_env", return_value=Path("/tmp/gaas-env.json"))
@patch("gaas.phases._find_repo_root")
@patch("gaas.phases.get_run_log")
def test_phase_install_frontends_no_mid_run_confirm(
    mock_get_run_log,
    mock_repo_root,
    _write_env,
    mock_frontend_dist,
    mock_casals_dist,
    mock_deploy_assets,
    _mock_principal,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    dist = repo_root / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    mock_repo_root.return_value = repo_root
    mock_frontend_dist.return_value = dist
    mock_casals_dist.return_value = dist

    run_log = MagicMock()
    run_log.run_step = MagicMock()
    mock_get_run_log.return_value = run_log

    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "realm_registry_frontend": VALID_CANISTER_ID,
        "file_registry_frontend": VALID_CANISTER_ID,
        "casals_frontend": VALID_CANISTER_ID,
        "casals_backend": VALID_CANISTER_ID,
    }
    data["services"] = {"monitor_url": "https://casals.realmsops.dev/v1/realms-test"}
    descriptor = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic", yes=False, work_dir=tmp_path / "work")

    phase_install_frontends(descriptor, ctx)

    # npm install + realm_registry_frontend build; file_registry_frontend uses
    # committed dist (no extra npm). marketplace_frontend is absent so skipped.
    assert run_log.run_step.call_count == 2
    assert mock_deploy_assets.call_count == 3
    for call in mock_deploy_assets.call_args_list:
        assert call.kwargs.get("yes") is True
        assert call.kwargs.get("mode") == "reinstall"
    assert mock_casals_dist.call_args.kwargs["monitor_url"] == (
        "https://casals.realmsops.dev/v1/realms-test"
    )


@patch("gaas.phases.build_marketplace_frontend")
@patch("gaas.phases.dfx.get_principal", return_value="aaaaa-aa")
@patch("gaas.phases.dfx.deploy_assets_canister")
@patch("gaas.phases.resolve_casals_frontend_dist")
@patch("gaas.phases.frontend_dist_dir")
@patch("gaas.phases.write_gaas_env", return_value=Path("/tmp/gaas-env.json"))
@patch("gaas.phases._find_repo_root")
@patch("gaas.phases.get_run_log")
def test_phase_install_frontends_reinstalls_marketplace_onto_existing_id(
    mock_get_run_log,
    mock_repo_root,
    _write_env,
    mock_frontend_dist,
    mock_casals_dist,
    mock_deploy_assets,
    _mock_principal,
    mock_build_marketplace,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    dist = repo_root / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    mock_repo_root.return_value = repo_root
    mock_frontend_dist.return_value = dist
    mock_casals_dist.return_value = dist
    mock_get_run_log.return_value = MagicMock()

    marketplace_frontend_id = "ccccc-ccccc-ccccc-ccccc-ccc"
    marketplace_backend_id = "ddddd-ddddd-ddddd-ddddd-ddd"
    file_registry_id = "eeeee-eeeee-eeeee-eeeee-eee"
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "realm_registry_frontend": VALID_CANISTER_ID,
        "file_registry_frontend": VALID_CANISTER_ID,
        "casals_frontend": VALID_CANISTER_ID,
        "casals_backend": VALID_CANISTER_ID,
        "marketplace_frontend": marketplace_frontend_id,
        "marketplace_backend": marketplace_backend_id,
        "file_registry": file_registry_id,
    }
    descriptor = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic", yes=True, work_dir=tmp_path / "work")

    phase_install_frontends(descriptor, ctx)

    mock_build_marketplace.assert_called_once()
    assert mock_build_marketplace.call_args.kwargs["marketplace_backend_id"] == (
        marketplace_backend_id
    )
    assert mock_build_marketplace.call_args.kwargs["file_registry_id"] == file_registry_id
    assert mock_deploy_assets.call_count == 4
    marketplace_deploy = mock_deploy_assets.call_args_list[-1]
    assert marketplace_deploy.args[0] == "marketplace_frontend"
    assert marketplace_deploy.args[1] == marketplace_frontend_id
    assert marketplace_deploy.kwargs.get("mode") == "reinstall"


def _install_backends_descriptor() -> Descriptor:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "realm_registry_backend": VALID_CANISTER_ID,
        "realm_installer": VALID_CANISTER_ID,
        "casals_backend": VALID_CANISTER_ID,
    }
    return Descriptor.model_validate(data)


@patch("gaas.phases.dfx.install_wasm")
@patch("gaas.phases.dfx.detect_install_mode", return_value="upgrade")
@patch("gaas.phases.resolve_casals_wasm")
@patch("gaas.phases.resolve_platform_backend_wasm")
@patch("gaas.phases._find_repo_root")
def test_phase_install_backends_upgrades_by_default(
    _mock_repo_root,
    mock_platform_wasm,
    mock_casals_wasm,
    mock_detect,
    mock_install,
    tmp_path: Path,
) -> None:
    mock_platform_wasm.return_value = tmp_path / "platform.wasm.gz"
    mock_casals_wasm.return_value = tmp_path / "casals.wasm.gz"
    descriptor = _install_backends_descriptor()
    ctx = DeployContext(identity="deployer", network="ic", work_dir=tmp_path / "work")

    phase_install_backends(descriptor, ctx)

    assert mock_detect.call_count == 3
    assert mock_install.call_count == 3
    for call in mock_install.call_args_list:
        assert call.args[3] == "upgrade"


@patch("gaas.phases.dfx.install_wasm")
@patch("gaas.phases.dfx.detect_install_mode", return_value="upgrade")
@patch("gaas.phases.resolve_casals_wasm")
@patch("gaas.phases.resolve_platform_backend_wasm")
@patch("gaas.phases._find_repo_root")
def test_phase_install_backends_reinstall_backends_forces_wipe(
    _mock_repo_root,
    mock_platform_wasm,
    mock_casals_wasm,
    mock_detect,
    mock_install,
    tmp_path: Path,
) -> None:
    mock_platform_wasm.return_value = tmp_path / "platform.wasm.gz"
    mock_casals_wasm.return_value = tmp_path / "casals.wasm.gz"
    descriptor = _install_backends_descriptor()
    ctx = DeployContext(
        identity="deployer",
        network="ic",
        reinstall_backends=True,
        work_dir=tmp_path / "work",
    )

    phase_install_backends(descriptor, ctx)

    mock_detect.assert_not_called()
    assert mock_install.call_count == 3
    for call in mock_install.call_args_list:
        assert call.args[3] == "reinstall"


@patch("gaas.phases.configure_marketplace_backend")
@patch("gaas.phases.build_marketplace_backend_wasm")
@patch("gaas.phases.dfx.install_wasm")
@patch("gaas.phases.dfx.detect_install_mode", return_value="upgrade")
@patch("gaas.phases.resolve_casals_wasm")
@patch("gaas.phases.resolve_platform_backend_wasm")
@patch("gaas.phases._find_repo_root")
def test_phase_install_backends_installs_file_registry_and_marketplace(
    mock_repo_root,
    mock_platform_wasm,
    mock_casals_wasm,
    mock_detect,
    mock_install,
    mock_marketplace_wasm,
    mock_configure_marketplace,
    tmp_path: Path,
) -> None:
    mock_repo_root.return_value = tmp_path / "repo"
    mock_platform_wasm.return_value = tmp_path / "platform.wasm.gz"
    mock_casals_wasm.return_value = tmp_path / "casals.wasm.gz"
    mock_marketplace_wasm.return_value = tmp_path / "marketplace.wasm.gz"

    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "realm_registry_backend": VALID_CANISTER_ID,
        "realm_installer": VALID_CANISTER_ID,
        "casals_backend": VALID_CANISTER_ID,
        "file_registry": "aaaaa-aaaaa-aaaaa-aaaaa-aaa",
        "marketplace_backend": "bbbbb-bbbbb-bbbbb-bbbbb-bbb",
    }
    descriptor = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic", work_dir=tmp_path / "work")

    phase_install_backends(descriptor, ctx)

    assert mock_install.call_count == 5
    mock_marketplace_wasm.assert_called_once()
    mock_configure_marketplace.assert_called_once()
    installed_ids = [call.args[0] for call in mock_install.call_args_list]
    assert "aaaaa-aaaaa-aaaaa-aaaaa-aaa" in installed_ids
    assert "bbbbb-bbbbb-bbbbb-bbbbb-bbb" in installed_ids
