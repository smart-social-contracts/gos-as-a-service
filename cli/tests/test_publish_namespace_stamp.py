"""publish_namespace finalize must stamp first-party ext/codex approvals."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gaas.descriptor import Descriptor
from gaas.file_registry_client import publish_namespace
from gaas.main import app
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID

runner = CliRunner()


@patch("gaas.namespace_approval_seed.stamp_after_publish")
@patch("gaas.file_registry_client.dfx.canister_call")
def test_publish_namespace_stamps_ext_via_marketplace(
    mock_call: MagicMock,
    mock_stamp: MagicMock,
) -> None:
    mock_call.return_value = json.dumps({"ok": True, "namespace": "ext/voting/1.0.0"})
    mock_stamp.return_value = {
        "approved": True,
        "content_matches": True,
        "namespace": "ext/voting/1.0.0",
    }

    publish_namespace(
        "registry-id",
        "ext/voting/1.0.0",
        "ic",
        identity="deployer",
        marketplace_id="marketplace-id",
    )

    mock_call.assert_called_once()
    assert mock_call.call_args[0][1] == "publish_namespace"
    mock_stamp.assert_called_once_with(
        "registry-id",
        "ext/voting/1.0.0",
        "ic",
        "deployer",
        marketplace_id="marketplace-id",
    )


@patch("gaas.namespace_approval_seed.stamp_after_publish")
@patch("gaas.file_registry_client.dfx.canister_call")
def test_publish_namespace_does_not_skip_stamp_on_wasm(
    mock_call: MagicMock,
    mock_stamp: MagicMock,
) -> None:
    mock_call.return_value = json.dumps({"ok": True, "namespace": "wasm/realm-backend/0.4.0"})
    mock_stamp.return_value = None

    publish_namespace(
        "registry-id",
        "wasm/realm-backend/0.4.0",
        "ic",
        identity="deployer",
        marketplace_id="marketplace-id",
    )

    mock_stamp.assert_called_once()


def _descriptor(tmp_path: Path, *, name: str = "test", canisters: dict | None = None) -> Path:
    data = dict(SAMPLE_DESCRIPTOR)
    data["name"] = name
    data["canisters"] = canisters or {
        "file_registry": VALID_CANISTER_ID,
        "marketplace_backend": "mmmmm-mmmmm-mmmmm-mmmmm-mmmmm-mmm",
    }
    path = tmp_path / f"{name}.gaas.json"
    Descriptor.model_validate(data).save(path)
    return path


@patch("gaas.main.seed_namespace_approvals")
def test_stamp_namespace_approvals_command_forces_restamp(
    mock_seed: MagicMock,
    tmp_path: Path,
) -> None:
    path = _descriptor(tmp_path)
    mock_seed.return_value = {
        "granted": 1,
        "approved": 2,
        "skipped": 0,
        "failed": 0,
    }

    result = runner.invoke(
        app,
        [
            "stamp-namespace-approvals",
            str(path),
            "--identity",
            "deployer",
            "--network",
            "ic",
        ],
    )

    assert result.exit_code == 0, result.output
    mock_seed.assert_called_once()
    kwargs = mock_seed.call_args.kwargs
    assert kwargs["force"] is True
    assert "approved=2" in result.output


@patch("gaas.main.seed_namespace_approvals")
def test_stamp_namespace_approvals_command_refuses_demo(
    mock_seed: MagicMock,
    tmp_path: Path,
) -> None:
    path = _descriptor(tmp_path, name="demo")

    result = runner.invoke(
        app,
        [
            "stamp-namespace-approvals",
            str(path),
            "--identity",
            "deployer",
            "--network",
            "ic",
        ],
    )

    assert result.exit_code == 1
    assert "demo" in result.output
    mock_seed.assert_not_called()
