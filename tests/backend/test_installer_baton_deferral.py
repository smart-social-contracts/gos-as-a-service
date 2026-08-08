"""Tests for deferred Casals stand baton hand-off ordering."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from baton_deferral import (
    PROVISION_PIPELINE_STEPS,
    REGISTRATION_PIPELINE_STEPS,
    assert_baton_after_bootstrap,
    build_baton_handoff_payload,
    decode_baton_handoff_payload,
    encode_baton_handoff_payload,
    hand_targets_from_payload,
    should_record_deferred_baton,
    should_run_deferred_baton_handoff,
)


def test_baton_deferred_until_after_bootstrap_pipeline_order():
    assert_baton_after_bootstrap(PROVISION_PIPELINE_STEPS, REGISTRATION_PIPELINE_STEPS)


def test_should_record_deferred_baton_when_enabled_and_not_yet_handed_off():
    assert should_record_deferred_baton(
        create_stand_baton=True,
        baton_pending=0,
        baton_canister_id="",
    )
    assert not should_record_deferred_baton(
        create_stand_baton=False,
        baton_pending=0,
        baton_canister_id="",
    )
    assert not should_record_deferred_baton(
        create_stand_baton=True,
        baton_pending=0,
        baton_canister_id="abc-123",
    )


def test_should_run_deferred_baton_handoff_only_when_pending():
    assert should_run_deferred_baton_handoff(
        baton_pending=1,
        baton_canister_id="",
        create_stand_baton=True,
    )
    assert not should_run_deferred_baton_handoff(
        baton_pending=0,
        baton_canister_id="",
        create_stand_baton=True,
    )
    assert not should_run_deferred_baton_handoff(
        baton_pending=1,
        baton_canister_id="done",
        create_stand_baton=True,
    )
    assert not should_run_deferred_baton_handoff(
        baton_pending=1,
        baton_canister_id="",
        create_stand_baton=False,
    )


def test_baton_handoff_payload_roundtrip_includes_token_target():
    payload = build_baton_handoff_payload(
        stand="my-realm",
        casals_id="casals-principal",
        baton_key="orchestration-baton",
        hand_targets=[
            ("my-realm-backend", "be-id"),
            ("my-realm-frontend", "fe-id"),
            ("my-realm-token", "tok-id"),
        ],
        backend_id="be-id",
    )
    raw = encode_baton_handoff_payload(payload)
    decoded = decode_baton_handoff_payload(raw)
    assert hand_targets_from_payload(decoded) == [
        ("my-realm-backend", "be-id"),
        ("my-realm-frontend", "fe-id"),
        ("my-realm-token", "tok-id"),
    ]


def test_provision_steps_place_defer_before_extensions_schedule():
    defer_idx = PROVISION_PIPELINE_STEPS.index("defer_baton_record")
    quarter_idx = PROVISION_PIPELINE_STEPS.index("quarter_provisioning_config")
    ext_idx = PROVISION_PIPELINE_STEPS.index("extensions_or_registration_schedule")
    assert defer_idx < quarter_idx < ext_idx


def test_registration_steps_place_baton_before_registry():
    baton_idx = REGISTRATION_PIPELINE_STEPS.index("baton_handoff_execute")
    reg_idx = REGISTRATION_PIPELINE_STEPS.index("registry_register")
    config_idx = REGISTRATION_PIPELINE_STEPS.index("backend_canister_config")
    assert config_idx < baton_idx < reg_idx
