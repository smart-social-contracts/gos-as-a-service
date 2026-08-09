"""Tests for deployment phases."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gaas.descriptor import Descriptor, MultisigConfig, PlatformConfig, ServicesConfig
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
    phase_domain_wiring,
    phase_grant_commanders,
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
    mock_hashes.return_value = {"chora_backend.wasm.gz": "abc"}

    data = dict(SAMPLE_DESCRIPTOR)
    data["gos"] = [
        {
            "implementation": "chora-gos",
            "version": "v0.1.0",
            "release_repo": "smart-social-contracts/chora",
            "artifacts": {
                "backend_wasm_key": "chora-backend",
                "frontend_wasm_key": "chora-assets",
            },
            "loader_profile": "chora-iframe-v1",
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

    assert ctx.completed_phases == []


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
    # 1 adopted + 6 platform created; adopt-only marketplace names are skipped.
    assert len(desc.canisters) == 7
    assert "marketplace_backend" not in desc.canisters
    assert "marketplace_frontend" not in desc.canisters


def test_registry_init_json_open_mode() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    default_json = json.loads(_registry_config_json(desc))
    # No billing_url in SAMPLE_DESCRIPTOR → derived open mode, always explicit.
    assert default_json["open_mode"] is True
    assert default_json["portal_url"] == "https://test.gos.earth"

    open_desc = desc.model_copy(update={"flags": {"open_mode": True}})
    open_json = json.loads(_registry_config_json(open_desc))
    assert open_json["open_mode"] is True

    billed = desc.model_copy(
        update={
            "services": ServicesConfig(
                billing_url="https://billing.example.com",
                deploy_url=None,
            ),
            "flags": {"open_mode": True},
        }
    )
    billed_json = json.loads(_registry_config_json(billed))
    assert billed_json["open_mode"] is True

    # Billing present, nothing explicit → derived closed.
    billed_only = desc.model_copy(
        update={
            "services": ServicesConfig(
                billing_url="https://billing.example.com",
                deploy_url=None,
            ),
        }
    )
    assert json.loads(_registry_config_json(billed_only))["open_mode"] is False

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
    assert json.loads(_registry_config_json(alias))["open_mode"] is True

    # Explicit flag beats the deprecated alias.
    override = alias.model_copy(update={"flags": {"open_mode": False}})
    assert json.loads(_registry_config_json(override))["open_mode"] is False
    assert billed_json["billing_url"] == "https://billing.example.com"


def test_registry_config_json_installer_id_and_flags() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"realm_installer": VALID_CANISTER_ID}
    data["flags"] = {"open_mode": True}
    desc = Descriptor.model_validate(data)
    payload = json.loads(_registry_config_json(desc))
    assert payload["installer_id"] == VALID_CANISTER_ID
    assert payload["open_mode"] is True


def test_registry_runtime_config_json_open_mode() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    # No billing_url → derived open mode.
    ic_payload = json.loads(_registry_runtime_config_json(desc, "ic"))
    assert ic_payload == {
        "test_flags": {"test_mode": True, "ii_bypass": True},
    }

    open_desc = desc.model_copy(update={"flags": {"open_mode": True}})
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
def test_phase_configure_backends_open_mode_sets_runtime_flags(
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
            "open_mode": True,
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
    data["flags"] = {"open_mode": True}
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
            "open_mode": False,
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
        "casals_backend": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
    }
    desc = Descriptor.model_validate(data)
    payload = json.loads(_installer_config_json(desc))
    assert payload["registry_backend_id"] == VALID_CANISTER_ID
    assert payload["file_registry_id"] == "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aab"
    assert payload["casals_canister_id"] == "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb"
    assert payload["portal_url"] == "https://test.gos.earth"
    assert payload["provision_via_casals"] is True
    assert payload["create_stand_baton"] is True


def test_installer_config_json_casals_backend_key() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"casals_backend": VALID_CANISTER_ID}
    desc = Descriptor.model_validate(data)
    payload = json.loads(_installer_config_json(desc))
    assert payload["casals_canister_id"] == VALID_CANISTER_ID


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
    assert closed["default_min_cycles"] == 500_000_000_000
    assert "extra_controller_principals" not in closed

    open_desc = desc.model_copy(update={"flags": {"open_mode": True}})
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
    data["flags"] = {"open_mode": True}
    data["canisters"] = {
        "realm_registry_backend": VALID_CANISTER_ID,
        "realm_registry_frontend": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aab",
        "realm_installer": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
        "file_registry": "ccccc-ccccc-ccccc-ccccc-ccccc-ccc",
        "file_registry_frontend": "ddddd-ddddd-ddddd-ddddd-ddddd-ddd",
        "casals_backend": "eeeee-eeeee-eeeee-eeeee-eeeee-eee",
        "casals_frontend": "fffff-fffff-fffff-fffff-fffff-fff",
    }
    data["multisig"] = {"backend_id": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aac"}
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic")
    phase_controller_topology(desc, ctx)
    assert mock_update.call_count == 7
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
        '"billing_url":"","open_mode":true}"\n  }'
    )
    parsed = _parse_registry_configure(raw)
    assert parsed["success"] is True
    assert parsed["open_mode"] is True


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
