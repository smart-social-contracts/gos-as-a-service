"""Tests for the post-install bootstrap of a new realm (in-realm setup wizard, issue #8).

A Realms GOS backend takes ``run(name, json)`` / ``read(name, json)``; the
installer sets it up with ``setup_step`` and installs packages with
``extension_install`` / ``codex_install``.
"""

import json
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from bootstrap import (  # noqa: E402
    RELAX_TRUST_POLICY_STEP,
    branding_payload,
    build_enter_setup_candid,
    deploy_step_kinds,
    enter_setup_args,
    founder_error,
    gos_implementation,
    manifest_has_codex_block,
    needs_enter_setup_step,
    package_install_call,
    package_needs_version,
    realm_identity_payload,
    realm_reply,
    resolve_founder,
    resolve_legacy_install_lists,
    setup_entry_kind,
    setup_infrastructure_args,
    setup_infrastructure_payload,
    setup_install_args,
    setup_install_payload,
    realm_test_mode_payload,
    tokens_payload,
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


def _ext_manifest_for_job(manifest, baton=""):
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
        "installer_canister_id": "installer-id",
        "baton_canister_id": baton,
        "network": network,
        "can_test_mode": bool(manifest.get("can_test_mode")),
        "test_flags": manifest.get("test_flags") or {},
        "founder": (manifest.get("founder") or "").strip(),
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


def _infrastructure(manifest):
    args = setup_infrastructure_args(
        manifest, manifest["target_canister_id"], manifest["frontend_canister_id"]
    )
    return args, setup_infrastructure_payload(args)


# ── Which steps a deploy task has ──────────────────────────────────────

def test_manifest_without_codex_has_no_codex_block():
    manifest = _bootstrap_manifest()
    assert not manifest_has_codex_block(manifest)


def test_manifest_with_legacy_codex_has_codex_block():
    manifest = _legacy_codex_manifest()
    assert manifest_has_codex_block(manifest)


def test_deploy_steps_without_codex_only_bootstrap():
    ext_manifest = _ext_manifest_for_job(_bootstrap_manifest())
    assert deploy_step_kinds(ext_manifest) == [
        "setup_install",
        "setup_infrastructure",
        "grant_frontend_access",
    ]


def test_deploy_steps_with_codex_install_extensions_then_the_codex():
    """No codex_init step (codex_install runs init) and no frontend resync."""
    ext_manifest = _ext_manifest_for_job(_legacy_codex_manifest())
    assert deploy_step_kinds(ext_manifest) == [
        "setup_install",
        "setup_infrastructure",
        "grant_frontend_access",
        "extension",
        "codex",
    ]


def test_legacy_install_lists_resolve_extensions_and_codex():
    realm_info = _legacy_codex_manifest()["realm"]
    ext_list, codex_list = resolve_legacy_install_lists(realm_info)
    assert ext_list == [{"id": "ext-a"}]
    assert codex_list == [{"id": "my-codex", "version": "1.0.0"}]


def test_legacy_install_lists_accept_a_package_record():
    _, codex_list = resolve_legacy_install_lists(
        {"codex": {"package": {"name": "agora", "version": "2.1.0"}}}
    )
    assert codex_list == [{"id": "agora", "version": "2.1.0"}]


def test_ext_manifest_without_codex_omits_install_lists():
    ext_manifest = _ext_manifest_for_job(_bootstrap_manifest())
    assert "codices" not in ext_manifest
    assert "extensions" not in ext_manifest


# ── setup_step install ─────────────────────────────────────────────────

def test_setup_install_payload_carries_network_test_mode_and_founder():
    manifest = _bootstrap_manifest(can_test_mode=True, network="staging")
    args = setup_install_args(_ext_manifest_for_job(manifest), "backend-principal")
    assert args["backend_canister_id"] == "backend-principal"
    assert setup_install_payload(args) == {
        "step": "install",
        "network": "staging",
        "can_test_mode": True,
        "founder": "creator-principal-abc",
    }


def test_setup_install_founder_beats_requesting_principal():
    """The portal's II principal founds the realm, not the billing caller."""
    manifest = _bootstrap_manifest(
        requesting_principal="billing-caller", founder="portal-ii-principal",
    )
    payload = setup_install_payload(
        setup_install_args(_ext_manifest_for_job(manifest), "backend-principal")
    )
    assert payload["founder"] == "portal-ii-principal"


def test_setup_install_falls_back_to_requesting_principal_without_founder():
    manifest = _bootstrap_manifest(requesting_principal="creator-principal-abc")
    assert resolve_founder(manifest) == "creator-principal-abc"
    payload = setup_install_payload(setup_install_args(manifest, "backend-principal"))
    assert payload["founder"] == "creator-principal-abc"


def test_setup_install_without_test_mode_says_so():
    payload = setup_install_payload(setup_install_args(_bootstrap_manifest(), "be"))
    assert payload["can_test_mode"] is False
    assert payload["network"] == "test"


def test_founder_must_be_a_signed_in_principal():
    assert founder_error("creator-principal-abc") == ""
    assert "no founder" in founder_error("")
    assert "no founder" in founder_error("   ")
    assert "anonymous" in founder_error("2vxsx-fae")


# ── setup_step infrastructure (+ test flags, trust policy) ─────────────

def test_infrastructure_payload_lists_the_realms_canisters():
    manifest = _bootstrap_manifest(
        infra={
            "file_registry_canister_id": "live-file-registry",
            "marketplace_canister_id": "live-marketplace",
        },
    )
    _args, payload = _infrastructure(_ext_manifest_for_job(manifest, baton="baton-id"))
    assert payload == {
        "step": "infrastructure",
        "frontend_canister_id": "frontend-principal",
        "file_registry_canister_id": "live-file-registry",
        "marketplace_canister_id": "live-marketplace",
        "installer_canister_id": "installer-id",
        "baton_canister_id": "baton-id",
    }


def test_infrastructure_payload_omits_unknown_canisters():
    """No baked-in per-network defaults: an id nobody supplied is not sent at all."""
    _args, payload = _infrastructure(_bootstrap_manifest())
    assert payload == {"step": "infrastructure", "frontend_canister_id": "frontend-principal"}


def test_infrastructure_payload_prefers_top_level_marketplace_over_infra():
    manifest = _bootstrap_manifest(
        infra={
            "file_registry_canister_id": "infra-file-registry",
            "marketplace_canister_id": "infra-marketplace-id",
        },
        marketplace_canister_id="top-level-marketplace",
    )
    _args, payload = _infrastructure(manifest)
    assert payload["file_registry_canister_id"] == "infra-file-registry"
    assert payload["marketplace_canister_id"] == "top-level-marketplace"


def test_infrastructure_payload_sends_only_infrastructure_fields():
    """setup_step refuses any field outside the step's own (``cannot configure x here``)."""
    manifest = _bootstrap_manifest(can_test_mode=True, test_flags={"test_mode": True})
    _args, payload = _infrastructure(_ext_manifest_for_job(manifest, baton="b"))
    assert set(payload) - {"step"} <= {
        "frontend_canister_id", "file_registry_canister_id", "marketplace_canister_id",
        "installer_canister_id", "baton_canister_id",
    }


def test_infrastructure_falls_back_to_the_configured_file_registry():
    _reset_installer_config()
    apply_installer_config({"file_registry_id": "configured-registry"})
    try:
        _args, payload = _infrastructure(_bootstrap_manifest())
        assert payload["file_registry_canister_id"] == "configured-registry"
    finally:
        _reset_installer_config()


def test_test_flags_become_test_mode_and_test_mode_switches():
    manifest = _bootstrap_manifest(
        can_test_mode=True,
        test_flags={"test_mode": True, "ii_bypass": True, "skip_terms": False},
    )
    args, _payload = _infrastructure(_ext_manifest_for_job(manifest))
    assert realm_test_mode_payload(args["test_flags"]) == {
        "step": "realm",
        "test_mode": True,
        "test_flags": {"test_mode_ii_bypass": True, "test_mode_skip_terms": False},
    }


def test_test_flags_already_prefixed_are_kept():
    assert realm_test_mode_payload({"test_mode_demo_data": True})["test_flags"] == {
        "test_mode_demo_data": True,
    }


def test_no_test_flags_no_test_step():
    assert realm_test_mode_payload({}) == {}
    assert realm_test_mode_payload(None) == {}
    args, _payload = _infrastructure(_ext_manifest_for_job(_bootstrap_manifest()))
    assert realm_test_mode_payload(args["test_flags"]) == {}


def test_trust_policy_step_turns_off_marketplace_approval():
    assert RELAX_TRUST_POLICY_STEP == {"step": "trust_policy", "require_marketplace_approval": False}


# ── Packages ───────────────────────────────────────────────────────────

def test_extension_install_names_the_extension_and_version():
    assert package_install_call("extension", "vault", "1.2.0") == (
        "extension_install", {"extension": "vault", "version": "1.2.0"},
    )


def test_codex_install_names_the_codex_and_version():
    assert package_install_call("codex", "agora", "3.0.0") == (
        "codex_install", {"codex": "agora", "version": "3.0.0"},
    )


def test_a_package_without_a_version_resolves_the_latest_first():
    for missing in (None, "", " ", "latest", "LATEST", "None"):
        assert package_needs_version(missing) is True
    assert package_needs_version("1.0.0") is False


# ── Registration-time setup steps ──────────────────────────────────────

def test_identity_step_names_the_realm():
    """The wizard never asks for the name and setup_launch refuses a nameless realm."""
    payload = realm_identity_payload(
        {"name": "my-realm", "display_name": "My Realm", "manifesto": "M", "welcome_message": "W"}
    )
    assert payload == {
        "step": "realm",
        "name": "My Realm",
        "manifesto": "M",
        "welcome_message": "W",
        "open_registration": False,
    }


def test_identity_step_leaves_registration_to_the_codex():
    payload = realm_identity_payload(
        {"name": "r", "codex": {"package": "agora"}, "open_registration": True}
    )
    assert "open_registration" not in payload


def test_identity_step_without_codex_passes_open_registration():
    assert realm_identity_payload({"name": "r", "open_registration": True})["open_registration"] is True


def test_identity_step_does_not_send_codex_parameters():
    """config_overrides has no setup_step field; the realm would refuse the whole step."""
    payload = realm_identity_payload({"name": "r", "config_overrides": {"quorum": 3}})
    assert "config_overrides" not in payload


def test_tokens_step_carries_nft_and_shared_ledgers():
    tokens = {"RLM": {"ledger": "rlm-ledger", "decimals": 8}}
    assert tokens_payload("nft-1", tokens) == {
        "step": "tokens", "nft_canister_id": "nft-1", "shared_tokens_json": tokens,
    }
    assert tokens_payload("", tokens) == {"step": "tokens", "shared_tokens_json": tokens}


def test_no_tokens_no_tokens_step():
    assert tokens_payload("", {}) == {}
    assert tokens_payload("  ", None) == {}


def test_branding_points_at_the_file_registry():
    branding = {
        "file_registry_canister_id": "fr-1",
        "namespace": "branding-my-realm-abc123",
        "files": {"/custom/logo.png": "logo.png", "/custom/background.png": "background.png"},
    }
    assert branding_payload(branding) == {
        "step": "branding",
        "logo_url": "https://fr-1.icp0.io/branding-my-realm-abc123/logo.png",
        "background_image_url": "https://fr-1.icp0.io/branding-my-realm-abc123/background.png",
    }


def test_branding_uses_the_realms_file_registry_when_the_upload_names_none():
    payload = branding_payload(
        {"namespace": "ns", "files": {"/custom/logo.png": "/logo.png"}}, "fr-default",
    )
    assert payload == {"step": "branding", "logo_url": "https://fr-default.icp0.io/ns/logo.png"}


def test_no_branding_no_branding_step():
    assert branding_payload({}) == {}
    assert branding_payload({"namespace": "ns", "files": {}}, "fr") == {}
    assert branding_payload({"files": {"/custom/logo.png": "logo.png"}}, "fr") == {}
    assert branding_payload({"namespace": "ns", "files": {"/other.png": "x.png"}}, "fr") == {}


# ── Realm replies ──────────────────────────────────────────────────────

def test_realm_reply_ok():
    assert realm_reply('{"ok": true, "done": ["install"]}') == ({"ok": True, "done": ["install"]}, "")


def test_realm_reply_unwraps_a_one_value_tuple():
    assert realm_reply(('{"ok": true}',)) == ({"ok": True}, "")
    assert realm_reply(b'{"ok": true}') == ({"ok": True}, "")


def test_realm_reply_reports_the_realms_error():
    reply, error = realm_reply(json.dumps({"ok": False, "error": "setup_step needs realm.configure"}))
    assert error == "setup_step needs realm.configure"
    assert reply["ok"] is False


def test_realm_reply_without_ok_is_an_error():
    """Old-style replies (``success``) and junk do not count as done."""
    assert realm_reply('{"success": true}')[1]
    assert realm_reply("not-json")[1].startswith("unreadable realm reply")
    assert realm_reply(None)[1]


def test_realm_reply_filed_as_proposal_is_an_error():
    _reply, error = realm_reply(json.dumps({"ok": True, "proposal": "P-3", "requires_vote": True}))
    assert "proposal P-3" in error


# ── Monad GOS keeps its own enter_setup ────────────────────────────────

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
    assert setup_entry_kind(manifest) == "enter_setup"
    assert deploy_step_kinds(manifest) == ["enter_setup"]


def test_monad_gos_with_extensions_skips_infrastructure_and_grant():
    manifest = _bootstrap_manifest(
        gos={"implementation": "monad-gos"},
        extensions=[{"id": "leftover-ext"}],
    )
    kinds = deploy_step_kinds(manifest)
    assert "setup_infrastructure" not in kinds
    assert "grant_frontend_access" not in kinds
    assert kinds[0] == "enter_setup"
    assert "extension" in kinds


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


def test_enter_setup_args_uses_founder_over_requesting_principal():
    manifest = _bootstrap_manifest(
        requesting_principal="billing-caller",
        founder="portal-ii-principal",
    )
    args = enter_setup_args(manifest, manifest["target_canister_id"])
    assert args["creator_principal"] == "portal-ii-principal"


def test_enter_setup_candid_is_principal_plus_two_texts():
    candid = build_enter_setup_candid(
        "2eqns-rmzes-7npxw-dxpw2-qdy2s-mw6ix-svdo2-oya7o-a6ldc-sqgwh-bqe",
        "fntsr-aqaaa-aaaae-ag22a-cai",
        "staging",
    )
    assert candid == (
        '(principal "2eqns-rmzes-7npxw-dxpw2-qdy2s-mw6ix-svdo2-oya7o-a6ldc-sqgwh-bqe", '
        '"fntsr-aqaaa-aaaae-ag22a-cai", "staging")'
    )


def test_realms_gos_explicit_gets_setup_install_and_infrastructure():
    manifest = _bootstrap_manifest(
        gos={"implementation": "realms-gos"},
    )
    assert uses_realms_bootstrap(manifest)
    assert setup_entry_kind(manifest) == "setup_install"
    assert deploy_step_kinds(manifest) == [
        "setup_install",
        "setup_infrastructure",
        "grant_frontend_access",
    ]


def test_blank_gos_implementation_is_realms_gos():
    manifest = _bootstrap_manifest(gos={"implementation": ""})
    assert uses_realms_bootstrap(manifest)
    assert deploy_step_kinds(manifest) == [
        "setup_install",
        "setup_infrastructure",
        "grant_frontend_access",
    ]


# ── Wiring in the canister module (not importable without basilisk) ────

def _installer_source() -> str:
    with open(os.path.join(_REPO_ROOT, "src/realm_installer/main.py"), encoding="utf-8") as fh:
        return fh.read()


def _section(src: str, start: str, end: str) -> str:
    return src.split(start, 1)[1].split(end, 1)[0]


def test_realm_service_declares_only_run_and_read():
    service = _section(_installer_source(), "class RealmTargetService(Service):", "class RealmRegistryService")
    assert '_arg_types = {"run": "text", "read": "text"}' in service
    assert "def run(self, name: text, args: text) -> text" in service
    assert "def read(self, name: text, args: text) -> text" in service
    assert "@service_query\n    def read" in service


def test_no_old_realm_method_is_called():
    src = _installer_source()
    for old in (
        "enter_setup_already_satisfied", "register_founder", "set_canister_config_json",
        "update_realm_config", "install_branding_from_registry", "install_extension_from_registry",
        "install_codex_from_registry", "run_codex_init", "resync_extension_frontends",
        "store_admin_invite_hash", "set_quarter_provisioning_config", "pin_directory",
    ):
        assert old not in src, old


def test_the_installer_never_launches_the_realm():
    """The founder launches from the wizard (setup_launch)."""
    assert "setup_launch" not in _installer_source()


def test_setup_install_step_refuses_a_missing_founder_before_calling():
    body = _section(_installer_source(), "def _execute_setup_install", "def _execute_setup_infrastructure")
    assert body.index("founder_error(") < body.index('_realm_call(backend_id, "setup_step"')


def test_infrastructure_step_order():
    """Canisters first (a failure fails the step), then test flags, then the trust policy."""
    body = _section(_installer_source(), "def _execute_setup_infrastructure", "def _relax_trust_policy")
    infra = body.index("setup_infrastructure_payload(args)")
    flags = body.index("realm_test_mode_payload(")
    trust = body.index("_relax_trust_policy(task, backend_id)")
    assert infra < flags < trust


def test_package_step_resolves_a_missing_version_from_the_file_registry():
    body = _section(_installer_source(), "def _execute_package_install", "def _execute_enter_setup")
    assert "package_needs_version(version)" in body
    assert "_latest_package_version(task.registry_canister_id" in body
    assert "package_install_call(step.kind" in body


def test_registration_sets_identity_tokens_and_branding_on_realms_gos_only():
    body = _section(_installer_source(), "def schedule_registration", "def _count_expected_steps")
    assert "uses_realms_bootstrap(manifest)" in body
    for payload in ("realm_identity_payload(", "tokens_payload(", "branding_payload("):
        assert payload in body
    assert body.index("realm_identity_payload(") < body.index("registry.register_realm(")
    # A nameless realm cannot launch; tokens and branding stay warnings.
    assert "setup_step realm (name) failed" in body
    assert body.index("setup_step realm (name) failed") < body.index("registry.register_realm(")


def test_destroy_reads_the_stage_from_realm_info():
    body = _section(_installer_source(), "def _fetch_realm_stage_gen", "def _destroy_realm_canisters_gen")
    assert '_realm_call(backend_id, "realm_info", {}, query=True)' in body
    assert '.get("status")' in body


def test_casals_path_passes_the_stand_baton_to_the_deploy_task():
    body = _section(_installer_source(), "def _provision_via_casals_body", "def _provision_ok_for_job")
    assert "_start_extensions_for_job(job, manifest, stand_baton_id(stand, ready))" in body
