"""Tests for deployment phases."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gaas.descriptor import Descriptor, PlatformConfig, ServicesConfig
from gaas.phases import (
    PHASES,
    DeployContext,
    _installer_config_json,
    _opt_text_init_arg,
    _registry_config_json,
    _resolve_open_mode,
    phase_create_canisters,
    phase_domain_wiring,
    phase_seed_file_registry,
    run_phases,
)
from gaas.gaas_env import build_gaas_env
from gaas.dfx import detect_install_mode
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID


def test_phases_order() -> None:
    ids = [phase_id for phase_id, _title, _func in PHASES]
    assert ids == [
        "validate",
        "create_canisters",
        "install_backends",
        "configure_backends",
        "seed_file_registry",
        "install_frontends",
        "domain_wiring",
        "smoke_checks",
    ]


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
    ]
    mock_ledger_create.return_value = "eeeee-eeeee-eeeee-eeeee-eeeee-eee"

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
    assert len(desc.canisters) == 7


def test_registry_init_json_open_mode() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    open_json = json.loads(_registry_config_json(desc))
    assert open_json["open_mode"] is True
    assert open_json["portal_url"] == "https://test.gos.earth"

    billed = desc.model_copy(
        update={
            "services": ServicesConfig(
                billing_url="https://billing.example.com",
                deploy_url=None,
            )
        }
    )
    billed_json = json.loads(_registry_config_json(billed))
    assert billed_json["open_mode"] is False
    assert billed_json["billing_url"] == "https://billing.example.com"


def test_registry_init_json_open_mode_explicit() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    billed_open = desc.model_copy(
        update={
            "services": ServicesConfig(
                billing_url="https://billing.example.com",
                open_mode=True,
            )
        }
    )
    assert json.loads(_registry_config_json(billed_open))["open_mode"] is True
    assert _resolve_open_mode(billed_open) is True

    forced_closed = desc.model_copy(
        update={"services": ServicesConfig(open_mode=False)}
    )
    assert json.loads(_registry_config_json(forced_closed))["open_mode"] is False
    assert _resolve_open_mode(forced_closed) is False


def test_installer_config_json_includes_ids() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "realm_registry_backend": VALID_CANISTER_ID,
        "file_registry": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aab",
        "casals_conductor": "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
    }
    desc = Descriptor.model_validate(data)
    payload = json.loads(_installer_config_json(desc))
    assert payload["registry_backend_id"] == VALID_CANISTER_ID
    assert payload["file_registry_id"] == "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aab"
    assert payload["casals_canister_id"] == "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb"
    assert payload["portal_url"] == "https://test.gos.earth"


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


@patch("gaas.phases.ensure_version_catalog_entry")
@patch("gaas.phases.seed_gos_entry")
@patch("gaas.phases.fetch_release_assets")
@patch("gaas.phases.namespace_published", return_value=False)
def test_seed_phase_publishes_version_catalog(
    _namespace_published,
    mock_fetch_assets,
    mock_seed,
    mock_publish,
    tmp_path: Path,
) -> None:
    backend = tmp_path / "realm_backend.wasm.gz"
    frontend = tmp_path / "realm_frontend.tar.gz"
    backend.write_bytes(b"wasm")
    frontend.write_bytes(b"tar")
    mock_fetch_assets.return_value = [backend, frontend]
    mock_publish.return_value = "published"

    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "file_registry": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aab",
        "realm_registry_backend": VALID_CANISTER_ID,
    }
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="default", network="ic")

    phase_seed_file_registry(desc, ctx)

    mock_seed.assert_called_once()
    mock_publish.assert_called_once()
    args = mock_publish.call_args[0]
    assert args[0] == VALID_CANISTER_ID
    assert args[2] == "0.3.1"
    assert args[3] == "wasm/realm-backend/0.3.1"
    assert args[4] == "frontend/realm-assets/0.3.1"
    assert args[5] == "realm_backend.wasm.gz"


@patch("gaas.phases.ensure_version_catalog_entry", return_value="skipped")
@patch("gaas.phases.fetch_namespace_hashes", return_value={"realm_backend.wasm.gz": "abc123"})
@patch("gaas.phases.namespace_published", return_value=True)
def test_seed_phase_skips_publish_when_already_cataloged(
    _namespace_published,
    _fetch_hashes,
    mock_publish,
) -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "file_registry": "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aab",
        "realm_registry_backend": VALID_CANISTER_ID,
    }
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="default", network="ic")

    phase_seed_file_registry(desc, ctx)

    mock_publish.assert_called_once()
    assert mock_publish.return_value == "skipped"
