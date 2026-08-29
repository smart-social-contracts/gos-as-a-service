"""Tests for file-registry namespace approval seeding."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from gaas.descriptor import Descriptor
from gaas.namespace_approval_seed import (
    ApprovalStampError,
    approval_matches_current_hash,
    assert_namespace_approved,
    candid_two_text,
    installable_namespaces_from_list,
    is_installable_namespace,
    needs_approval,
    refuse_demo_environment,
    seed_namespace_approvals,
    stamp_after_publish,
)
from gaas.phases import DeployContext, phase_seed_namespace_approvals
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID


def test_is_installable_namespace_filters_prefixes() -> None:
    assert is_installable_namespace("ext/voting/1.0.0")
    assert is_installable_namespace("codex/syntropia/1.0.0")
    assert not is_installable_namespace("wasm/realm-backend/0.4.0")
    assert not is_installable_namespace("frontend/realm-assets/0.4.0")
    assert not is_installable_namespace("branding/demo/logo")


def test_installable_namespaces_from_list() -> None:
    entries = [
        {"namespace": "ext/voting/1.0.0", "approved": False},
        {"namespace": "wasm/realm-backend/0.4.0"},
        {"namespace": "codex/syntropia/1.0.0", "approved": True},
    ]
    assert installable_namespaces_from_list(entries) == [
        "ext/voting/1.0.0",
        "codex/syntropia/1.0.0",
    ]


def test_needs_approval() -> None:
    assert needs_approval({"approved": False})
    assert needs_approval({})
    assert not needs_approval({"approved": True})


def test_candid_two_text_escapes_quotes() -> None:
    assert candid_two_text('say "hi"', "line\\two") == r'("say \"hi\"", "line\\two")'


def test_seed_namespace_approvals_skips_when_ids_missing() -> None:
    with patch("gaas.namespace_approval_seed.dfx.canister_call") as mock_call:
        result = seed_namespace_approvals("", "marketplace-id", "ic", "deployer")
        assert result == {"granted": 0, "approved": 0, "skipped": 0, "failed": 0}
        mock_call.assert_not_called()

        result = seed_namespace_approvals("registry-id", "", "ic", "deployer")
        assert result == {"granted": 0, "approved": 0, "skipped": 0, "failed": 0}
        mock_call.assert_not_called()


@patch("gaas.namespace_approval_seed.dfx.canister_call")
def test_seed_namespace_approvals_grant_then_approve(mock_call: MagicMock) -> None:
    namespaces = [
        {"namespace": "ext/voting/1.0.0", "approved": False},
        {"namespace": "ext/welcome/1.0.0", "approved": True},
        {"namespace": "wasm/realm-backend/0.4.0", "approved": False},
        {"namespace": "codex/syntropia/1.0.0", "approved": False},
    ]

    def side_effect(canister_id, method, arg, network, **kwargs):
        if method == "list_namespaces":
            return json.dumps(namespaces)
        if method == "admin_approve_namespace":
            return json.dumps({"success": True, "namespace": "ext/voting/1.0.0"})
        if method == "get_namespace_approval":
            return json.dumps(
                {
                    "approved": True,
                    "content_matches": True,
                    "status": "approved",
                    "namespace": "ext/voting/1.0.0",
                }
            )
        return json.dumps({"ok": True})

    mock_call.side_effect = side_effect

    result = seed_namespace_approvals(
        "registry-id",
        "marketplace-id",
        "ic",
        "deployer",
    )

    assert result == {"granted": 1, "approved": 2, "skipped": 1, "failed": 0}
    assert mock_call.call_args_list[0][0][0] == "registry-id"
    assert mock_call.call_args_list[0][0][1] == "grant_publish"
    grant_arg = mock_call.call_args_list[0][0][2]
    assert "_approvers" in grant_arg
    assert "marketplace-id" in grant_arg
    assert mock_call.call_args_list[1][0][1] == "list_namespaces"
    assert mock_call.call_args_list[1][0][2] == "()"
    approve_calls = [
        call
        for call in mock_call.call_args_list
        if call[0][1] == "admin_approve_namespace"
    ]
    assert len(approve_calls) == 2
    assert approve_calls[0][0][0] == "marketplace-id"


@patch("gaas.namespace_approval_seed.dfx.canister_call")
def test_seed_namespace_approvals_raises_when_all_fail(mock_call: MagicMock) -> None:
    mock_call.side_effect = [
        json.dumps({"ok": True}),
        json.dumps([{"namespace": "ext/voting/1.0.0", "approved": False}]),
        json.dumps({"success": False, "error": "refused"}),
    ]

    with pytest.raises(RuntimeError, match="all 1 namespace approval"):
        seed_namespace_approvals(
            "registry-id",
            "marketplace-id",
            "ic",
            "deployer",
        )


@patch("gaas.phases.seed_namespace_approvals")
def test_phase_seed_namespace_approvals_skips_missing_canisters(
    mock_seed: MagicMock,
) -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    ctx = DeployContext(identity="deployer", network="ic")

    phase_seed_namespace_approvals(desc, ctx)

    mock_seed.assert_not_called()


@patch("gaas.phases.seed_namespace_approvals")
def test_phase_seed_namespace_approvals_calls_seed(
    mock_seed: MagicMock,
) -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        **data.get("canisters", {}),
        "file_registry": VALID_CANISTER_ID,
        "marketplace_backend": "mmmmm-mmmmm-mmmmm-mmmmm-mmmmm-mmm",
    }
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="deployer", network="ic")
    mock_seed.return_value = {
        "granted": 1,
        "approved": 2,
        "skipped": 3,
        "failed": 0,
    }

    phase_seed_namespace_approvals(desc, ctx)

    mock_seed.assert_called_once_with(
        VALID_CANISTER_ID,
        "mmmmm-mmmmm-mmmmm-mmmmm-mmmmm-mmm",
        "ic",
        "deployer",
        force=True,
    )


@patch("gaas.phases.seed_namespace_approvals")
def test_phase_seed_namespace_approvals_warns_on_local_failure(
    mock_seed: MagicMock,
) -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {
        "file_registry": VALID_CANISTER_ID,
        "marketplace_backend": "mmmmm-mmmmm-mmmmm-mmmmm-mmmmm-mmm",
    }
    desc = Descriptor.model_validate(data)
    ctx = DeployContext(identity="default", network="local")
    mock_seed.side_effect = RuntimeError("all 3 namespace approval attempt(s) failed")

    phase_seed_namespace_approvals(desc, ctx)


def _approved_payload(namespace: str) -> str:
    return json.dumps(
        {
            "namespace": namespace,
            "approved": True,
            "content_matches": True,
            "status": "approved",
        }
    )


@patch("gaas.namespace_approval_seed.dfx.canister_call")
def test_stamp_after_publish_ext_is_approved_with_matching_hash(
    mock_call: MagicMock,
) -> None:
    """Publish finalize of an ext/ namespace leaves approved + content_matches."""

    def side_effect(canister_id, method, arg, network, **kwargs):
        if method == "admin_approve_namespace":
            return json.dumps({"success": True, "namespace": "ext/voting/1.0.0"})
        if method == "get_namespace_approval":
            return _approved_payload("ext/voting/1.0.0")
        return json.dumps({"ok": True})

    mock_call.side_effect = side_effect

    payload = stamp_after_publish(
        "registry-id",
        "ext/voting/1.0.0",
        "ic",
        "deployer",
        marketplace_id="marketplace-id",
    )

    assert payload is not None
    assert approval_matches_current_hash(payload)
    methods = [call[0][1] for call in mock_call.call_args_list]
    assert methods == [
        "grant_publish",
        "admin_approve_namespace",
        "get_namespace_approval",
    ]
    assert mock_call.call_args_list[1][0][0] == "marketplace-id"


@patch("gaas.namespace_approval_seed.dfx.canister_call")
def test_stamp_after_publish_restamps_on_republish(mock_call: MagicMock) -> None:
    mock_call.side_effect = [
        json.dumps({"ok": True}),
        json.dumps({"success": True, "namespace": "ext/voting/1.0.0"}),
        _approved_payload("ext/voting/1.0.0"),
        json.dumps({"ok": True}),
        json.dumps({"success": True, "namespace": "ext/voting/1.0.0"}),
        _approved_payload("ext/voting/1.0.0"),
    ]

    first = stamp_after_publish(
        "registry-id",
        "ext/voting/1.0.0",
        "ic",
        "deployer",
        marketplace_id="marketplace-id",
    )
    second = stamp_after_publish(
        "registry-id",
        "ext/voting/1.0.0",
        "ic",
        "deployer",
        marketplace_id="marketplace-id",
    )

    assert approval_matches_current_hash(first)
    assert approval_matches_current_hash(second)
    approve_calls = [
        call
        for call in mock_call.call_args_list
        if call[0][1] == "admin_approve_namespace"
    ]
    assert len(approve_calls) == 2


@patch("gaas.namespace_approval_seed.dfx.canister_call")
def test_stamp_after_publish_skips_wasm_namespace(mock_call: MagicMock) -> None:
    assert (
        stamp_after_publish(
            "registry-id",
            "wasm/realm-backend/0.4.0",
            "ic",
            "deployer",
            marketplace_id="marketplace-id",
        )
        is None
    )
    mock_call.assert_not_called()


def test_stamp_after_publish_requires_marketplace_on_ic() -> None:
    with pytest.raises(ApprovalStampError, match="without a marketplace approval stamp"):
        stamp_after_publish(
            "registry-id",
            "ext/voting/1.0.0",
            "ic",
            "deployer",
            marketplace_id=None,
        )


@patch("gaas.namespace_approval_seed.dfx.canister_call")
def test_stamp_after_publish_skips_missing_marketplace_on_local(
    mock_call: MagicMock,
) -> None:
    assert (
        stamp_after_publish(
            "registry-id",
            "ext/voting/1.0.0",
            "local",
            "deployer",
            marketplace_id="",
        )
        is None
    )
    mock_call.assert_not_called()


@patch("gaas.namespace_approval_seed.dfx.canister_call")
def test_stamp_after_publish_fails_when_content_does_not_match(
    mock_call: MagicMock,
) -> None:
    mock_call.side_effect = [
        json.dumps({"ok": True}),
        json.dumps({"success": True}),
        json.dumps(
            {
                "namespace": "ext/voting/1.0.0",
                "approved": False,
                "content_matches": False,
                "status": "approved",
            }
        ),
    ]

    with pytest.raises(ApprovalStampError, match="content_matches"):
        stamp_after_publish(
            "registry-id",
            "ext/voting/1.0.0",
            "ic",
            "deployer",
            marketplace_id="marketplace-id",
        )


@patch("gaas.namespace_approval_seed.dfx.canister_call")
def test_seed_force_restamps_already_approved(mock_call: MagicMock) -> None:
    def side_effect(canister_id, method, arg, network, **kwargs):
        if method == "list_namespaces":
            return json.dumps(
                [{"namespace": "ext/voting/1.0.0", "approved": True}]
            )
        if method == "admin_approve_namespace":
            return json.dumps({"success": True})
        if method == "get_namespace_approval":
            return _approved_payload("ext/voting/1.0.0")
        return json.dumps({"ok": True})

    mock_call.side_effect = side_effect
    result = seed_namespace_approvals(
        "registry-id",
        "marketplace-id",
        "ic",
        "deployer",
        force=True,
    )
    assert result["approved"] == 1
    assert result["skipped"] == 0


def test_refuse_demo_environment() -> None:
    with pytest.raises(ApprovalStampError, match="demo"):
        refuse_demo_environment("demo")
    refuse_demo_environment("test")
    refuse_demo_environment("staging")


def test_assert_namespace_approved_requires_hash_match() -> None:
    payload = {
        "namespace": "ext/voting/1.0.0",
        "approved": True,
        "content_matches": True,
    }
    assert assert_namespace_approved(payload, namespace="ext/voting/1.0.0") == payload
    with pytest.raises(ApprovalStampError, match="not approved"):
        assert_namespace_approved(
            {"approved": True, "content_matches": False},
            namespace="ext/voting/1.0.0",
        )
