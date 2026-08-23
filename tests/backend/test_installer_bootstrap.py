"""Tests for slimmed post-install bootstrap (in-realm setup wizard, issue #8)."""

import json
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from bootstrap import (  # noqa: E402
    configure_canister_ids_args,
    configure_canister_ids_payload,
    deploy_step_kinds,
    enter_setup_args,
    gos_implementation,
    manifest_has_codex_block,
    needs_enter_setup_step,
    resolve_legacy_install_lists,
    resync_extension_frontends_args,
    uses_monad_gos_bootstrap,
    uses_realms_bootstrap,
)
from installer_config import (  # noqa: E402
    InstallerConfig,
    apply_installer_config,
)


def _reset_installer_config():
    cfg = InstallerConfig["singleton"]
    if cfg:
        cfg.delete()
    list(InstallerConfig.instances())


def _bootstrap_manifest(**overrides):
    base = {
        "target_canister_id": "backend-principal",
        "frontend_canister_id": "frontend-principal",
        "registry_canister_id": "realm-registry-id",
        "network": "test",
        "requesting_principal": "creator-principal-abc",
        "federation": {"portal_url": "https://portal.example/r/my-realm"},
        "realm": {},
    }
    base.update(overrides)
    return base


def _legacy_codex_manifest(**overrides):
    return _bootstrap_manifest(
        realm={
            "extensions": [{"id": "ext-a"}],
            "codex": {"package": "my-codex", "version": "1.0.0"},
        },
        **overrides,
    )


def _ext_manifest_for_job(manifest):
    """Build the deploy-task manifest shape used after _start_extensions_for_job."""
    network = (manifest.get("network") or "").strip()
    realm_registry_id = (
        manifest.get("realm_registry_canister_id")
        or manifest.get("registry_canister_id")
        or ""
    )
    ext_manifest = {
        "target_canister_id": manifest["target_canister_id"],
        "frontend_canister_id": manifest["frontend_canister_id"],
        "realm_registry_canister_id": realm_registry_id,
        "infra": manifest.get("infra") or {},
        "network": network,
        "requesting_principal": manifest.get("requesting_principal", ""),
        "federation": manifest.get("federation") or {},
    }
    if manifest_has_codex_block(manifest):
        ext_list, codex_list = resolve_legacy_install_lists(manifest.get("realm") or {})
        if ext_list:
            ext_manifest["extensions"] = ext_list
        if codex_list:
            ext_manifest["codices"] = codex_list
    return ext_manifest


def test_manifest_without_codex_has_no_codex_block():
    manifest = _bootstrap_manifest()
    assert not manifest_has_codex_block(manifest)


def test_manifest_with_legacy_codex_has_codex_block():
    manifest = _legacy_codex_manifest()
    assert manifest_has_codex_block(manifest)


def test_deploy_steps_without_codex_only_bootstrap():
    ext_manifest = _ext_manifest_for_job(_bootstrap_manifest())
    assert deploy_step_kinds(ext_manifest) == [
        "enter_setup",
        "configure_canister_ids",
        "grant_frontend_access",
    ]


def test_deploy_steps_with_legacy_codex_includes_installs():
    ext_manifest = _ext_manifest_for_job(_legacy_codex_manifest())
    kinds = deploy_step_kinds(ext_manifest)
    assert kinds[:3] == [
        "enter_setup",
        "configure_canister_ids",
        "grant_frontend_access",
    ]
    assert "extension" in kinds
    assert "codex" in kinds
    assert kinds[-1] == "resync_extension_frontends"


def test_configure_payload_includes_creator_and_portal_origin():
    manifest = _bootstrap_manifest()
    args = configure_canister_ids_args(
        manifest, manifest["target_canister_id"], manifest["frontend_canister_id"]
    )
    payload, warnings = configure_canister_ids_payload(args)
    assert warnings == []
    assert payload["creator_principal"] == "creator-principal-abc"
    assert payload["portal_origin"] == "https://portal.example"
    assert payload["frontend_canister_id"] == "frontend-principal"
    assert payload["realm_registry_canister_id"] == "realm-registry-id"
    assert "file_registry_canister_id" not in payload
    assert "marketplace_canister_id" not in payload


def test_configure_payload_realm_registry_from_explicit_field():
    manifest = _bootstrap_manifest(
        realm_registry_canister_id="explicit-realm-registry",
        registry_canister_id="injected-realm-registry",
    )
    args = configure_canister_ids_args(
        manifest, manifest["target_canister_id"], manifest["frontend_canister_id"]
    )
    payload, _warnings = configure_canister_ids_payload(args)
    assert payload["realm_registry_canister_id"] == "explicit-realm-registry"


def test_configure_payload_omits_realms_file_registry_and_marketplace():
    manifest = _bootstrap_manifest(
        infra={
            "file_registry_canister_id": "infra-file-registry",
            "marketplace_canister_id": "infra-marketplace-id",
        },
        marketplace_canister_id="top-level-marketplace",
    )
    args = configure_canister_ids_args(
        manifest, manifest["target_canister_id"], manifest["frontend_canister_id"]
    )
    payload, _warnings = configure_canister_ids_payload(args)
    assert "file_registry_canister_id" not in payload
    assert "marketplace_canister_id" not in payload
    assert "network" not in payload


def test_ext_manifest_configure_includes_realm_registry():
    ext_manifest = _ext_manifest_for_job(_bootstrap_manifest())
    configure_args = configure_canister_ids_args(
        ext_manifest,
        ext_manifest["target_canister_id"],
        ext_manifest["frontend_canister_id"],
    )
    payload, _warnings = configure_canister_ids_payload(configure_args)
    assert payload["realm_registry_canister_id"] == "realm-registry-id"
    assert "file_registry_canister_id" not in payload


def test_configure_missing_requesting_principal_warns_and_proceeds():
    manifest = _bootstrap_manifest(requesting_principal="")
    args = configure_canister_ids_args(
        manifest, manifest["target_canister_id"], manifest["frontend_canister_id"]
    )
    payload, warnings = configure_canister_ids_payload(args)
    assert "creator_principal" not in payload
    assert any("requesting_principal missing" in w for w in warnings)


def test_configure_portal_origin_falls_back_to_installer_config():
    _reset_installer_config()
    apply_installer_config({"portal_url": "https://configured.portal/"})
    manifest = _bootstrap_manifest(federation={})
    args = configure_canister_ids_args(
        manifest, manifest["target_canister_id"], manifest["frontend_canister_id"]
    )
    payload, _warnings = configure_canister_ids_payload(args)
    assert payload["portal_origin"] == "https://configured.portal"


def test_legacy_install_lists_resolve_extensions_and_codex():
    realm_info = _legacy_codex_manifest()["realm"]
    ext_list, codex_list = resolve_legacy_install_lists(realm_info)
    assert ext_list == [{"id": "ext-a"}]
    assert codex_list == [{"id": "my-codex", "version": "1.0.0", "run_init": True}]


def test_ext_manifest_without_codex_omits_install_lists():
    ext_manifest = _ext_manifest_for_job(_bootstrap_manifest())
    assert "codices" not in ext_manifest
    assert "extensions" not in ext_manifest
    configure_args = configure_canister_ids_args(
        ext_manifest,
        ext_manifest["target_canister_id"],
        ext_manifest["frontend_canister_id"],
    )
    payload, _warnings = configure_canister_ids_payload(configure_args)
    assert payload["creator_principal"] == "creator-principal-abc"


def test_configure_payload_includes_test_flags_and_can_test_mode():
    manifest = _bootstrap_manifest(
        can_test_mode=True,
        test_flags={"test_mode": True, "ii_bypass": True},
    )
    args = configure_canister_ids_args(
        manifest, manifest["target_canister_id"], manifest["frontend_canister_id"]
    )
    assert args["can_test_mode"] is True
    assert args["test_flags"] == {"test_mode": True, "ii_bypass": True}
    payload, _warnings = configure_canister_ids_payload(args)
    assert payload["can_test_mode"] is True
    assert payload["test_flags"] == {"test_mode": True, "ii_bypass": True}


def test_resync_extension_frontends_only_passes_frontend():
    manifest = _bootstrap_manifest(
        infra={"file_registry_canister_id": "infra-file-registry"},
    )
    args = resync_extension_frontends_args(manifest)
    assert args == {"frontend_canister_id": "frontend-principal"}


def test_casals_path_always_enters_bootstrap_phase():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    main_path = os.path.join(repo_root, "src/realm_installer/main.py")
    with open(main_path, encoding="utf-8") as fh:
        source = fh.read()
    assert "entering bootstrap/extensions phase (casals path)" in source
    assert "no extensions/codex; scheduling registration (casals path)" not in source


def test_monad_gos_skips_realms_bootstrap_steps():
    manifest = _bootstrap_manifest(
        gos={"implementation": "monad-gos"},
    )
    assert gos_implementation(manifest) == "monad-gos"
    assert uses_monad_gos_bootstrap(manifest)
    assert not uses_realms_bootstrap(manifest)
    assert deploy_step_kinds(manifest) == ["enter_setup"]


def test_monad_gos_with_extensions_skips_configure_and_grant():
    manifest = _bootstrap_manifest(
        gos={"implementation": "monad-gos"},
        extensions=[{"id": "leftover-ext"}],
    )
    kinds = deploy_step_kinds(manifest)
    assert "configure_canister_ids" not in kinds
    assert "grant_frontend_access" not in kinds
    assert kinds[0] == "enter_setup"
    assert "extension" in kinds
    assert "resync_extension_frontends" in kinds


def test_enter_setup_args_from_manifest():
    manifest = _bootstrap_manifest(
        gos={"implementation": "monad-gos"},
        registry_canister_id="realm-registry-id",
        requesting_principal="creator-principal-abc",
        network="staging",
    )
    args = enter_setup_args(manifest, manifest["target_canister_id"])
    assert args == {
        "backend_canister_id": "backend-principal",
        "creator_principal": "creator-principal-abc",
        "realm_registry_canister_id": "realm-registry-id",
        "environment": "staging",
    }
    assert needs_enter_setup_step(manifest, manifest["target_canister_id"])


def test_realms_gos_explicit_still_has_configure_and_grant():
    manifest = _bootstrap_manifest(
        gos={"implementation": "realms-gos"},
    )
    assert uses_realms_bootstrap(manifest)
    assert deploy_step_kinds(manifest) == [
        "enter_setup",
        "configure_canister_ids",
        "grant_frontend_access",
    ]


def test_blank_gos_implementation_gets_enter_setup_and_realms_bootstrap():
    manifest = _bootstrap_manifest(gos={"implementation": ""})
    assert uses_realms_bootstrap(manifest)
    assert deploy_step_kinds(manifest) == [
        "enter_setup",
        "configure_canister_ids",
        "grant_frontend_access",
    ]
