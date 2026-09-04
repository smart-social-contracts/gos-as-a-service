"""Tests for Casals CLI bootstrap wrapper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gaas.casals_cli import (
    CASALS_BOOTSTRAP_NAMES,
    casals_env,
    ids_file_payload,
    run_casals_new,
    run_casals_sheet_deploy,
)
from gaas.descriptor import Descriptor
from tests.conftest import CASALS_BOOTSTRAP_TEST_IDS, SAMPLE_DESCRIPTOR


def test_casals_env_ic_and_mainnet() -> None:
    assert casals_env("ic") == "ic"
    assert casals_env("mainnet") == "ic"


def test_casals_env_local_variants() -> None:
    assert casals_env("local") == "local"
    assert casals_env("localhost") == "local"
    assert casals_env("test") == "ic"
    assert casals_env("demo") == "ic"
    assert casals_env("staging") == "ic"


def test_ids_file_payload_maps_casals_file_registry() -> None:
    desc = Descriptor.model_validate(
        {
            **SAMPLE_DESCRIPTOR,
            "canisters": {
                "casals_backend": CASALS_BOOTSTRAP_TEST_IDS["casals_backend"],
                "casals_file_registry": CASALS_BOOTSTRAP_TEST_IDS["casals_file_registry"],
                "casals_file_registry_frontend": CASALS_BOOTSTRAP_TEST_IDS[
                    "casals_file_registry_frontend"
                ],
            },
        }
    )
    assert ids_file_payload(desc) == {
        "casals_backend": CASALS_BOOTSTRAP_TEST_IDS["casals_backend"],
        "ic_file_registry": CASALS_BOOTSTRAP_TEST_IDS["casals_file_registry"],
        "ic_file_registry_frontend": CASALS_BOOTSTRAP_TEST_IDS[
            "casals_file_registry_frontend"
        ],
    }


def test_ids_file_payload_empty_when_no_bootstrap_ids() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    assert ids_file_payload(desc) == {}


def _make_casals_checkout(tmp_path: Path) -> Path:
    casals = tmp_path / "Casals"
    casals.mkdir()
    (casals / "src").mkdir()
    (casals / "src" / "main.py").write_text("# casals\n", encoding="utf-8")
    (casals / "casals_backend.did").write_text("service : () -> ()\n", encoding="utf-8")
    (casals / "scripts").mkdir()
    (casals / "scripts" / "casals.py").write_text("# stub\n", encoding="utf-8")
    return casals


@patch("gaas.casals_cli.subprocess.run")
def test_run_casals_new_fresh_create(mock_run: MagicMock, tmp_path: Path) -> None:
    casals = _make_casals_checkout(tmp_path)
    stdout = json.dumps(
        {
            "ok": True,
            "mode": "create",
            "canisters": {
                "casals_backend": CASALS_BOOTSTRAP_TEST_IDS["casals_backend"],
                "casals_frontend": CASALS_BOOTSTRAP_TEST_IDS["casals_frontend"],
                "ic_file_registry": CASALS_BOOTSTRAP_TEST_IDS["casals_file_registry"],
                "ic_file_registry_frontend": CASALS_BOOTSTRAP_TEST_IDS[
                    "casals_file_registry_frontend"
                ],
            },
            "seeded": True,
        }
    )
    mock_run.return_value = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=stdout,
        stderr="",
    )

    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    result = run_casals_new(
        desc,
        network="ic",
        identity="deployer",
        casals_src=casals,
        yes=True,
    )

    assert result["mode"] == "create"
    for name in CASALS_BOOTSTRAP_NAMES:
        assert desc.canisters[name] == CASALS_BOOTSTRAP_TEST_IDS[name]

    argv = mock_run.call_args.args[0]
    assert "-y" in argv
    assert "--no-seed" in argv
    assert "--identity" in argv
    assert argv[argv.index("--identity") + 1] == "deployer"
    assert argv.index("--identity") < argv.index("new")
    assert not any(str(arg).endswith(".ids.json") for arg in argv)
    assert mock_run.call_args.kwargs["cwd"] == casals


@patch("gaas.casals_cli.canister_missing_on_ic", return_value=False)
@patch("gaas.casals_cli.subprocess.run")
def test_run_casals_new_adopt_passes_ids_file(
    mock_run: MagicMock, _mock_missing: MagicMock, tmp_path: Path
) -> None:
    casals = _make_casals_checkout(tmp_path)
    stdout = json.dumps(
        {
            "ok": True,
            "mode": "upgrade",
            "canisters": {
                "casals_backend": CASALS_BOOTSTRAP_TEST_IDS["casals_backend"],
                "casals_frontend": CASALS_BOOTSTRAP_TEST_IDS["casals_frontend"],
                "ic_file_registry": CASALS_BOOTSTRAP_TEST_IDS["casals_file_registry"],
                "ic_file_registry_frontend": CASALS_BOOTSTRAP_TEST_IDS[
                    "casals_file_registry_frontend"
                ],
            },
            "seeded": False,
        }
    )
    captured: dict[str, object] = {}

    def _run_side_effect(argv, **kwargs):
        ids_arg = next((arg for arg in argv if str(arg).endswith(".ids.json")), None)
        if ids_arg is not None:
            captured["payload"] = json.loads(Path(ids_arg).read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(
            args=argv,
            returncode=0,
            stdout=stdout,
            stderr="",
        )

    mock_run.side_effect = _run_side_effect

    desc = Descriptor.model_validate(
        {
            **SAMPLE_DESCRIPTOR,
            "canisters": {"casals_backend": CASALS_BOOTSTRAP_TEST_IDS["casals_backend"]},
        }
    )
    result = run_casals_new(
        desc,
        network="ic",
        identity="deployer",
        casals_src=casals,
    )

    assert result["mode"] == "upgrade"
    assert captured["payload"] == {
        "casals_backend": CASALS_BOOTSTRAP_TEST_IDS["casals_backend"],
    }
    argv = mock_run.call_args.args[0]
    assert "--no-seed" in argv


@patch("gaas.casals_cli.subprocess.run")
def test_run_casals_new_force_create_skips_ids_file(mock_run: MagicMock, tmp_path: Path) -> None:
    casals = _make_casals_checkout(tmp_path)
    stdout = json.dumps(
        {
            "ok": True,
            "mode": "create",
            "canisters": {
                "casals_backend": CASALS_BOOTSTRAP_TEST_IDS["casals_backend"],
                "casals_frontend": CASALS_BOOTSTRAP_TEST_IDS["casals_frontend"],
                "ic_file_registry": CASALS_BOOTSTRAP_TEST_IDS["casals_file_registry"],
                "ic_file_registry_frontend": CASALS_BOOTSTRAP_TEST_IDS[
                    "casals_file_registry_frontend"
                ],
            },
            "seeded": False,
        }
    )
    mock_run.return_value = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=stdout,
        stderr="",
    )

    desc = Descriptor.model_validate(
        {
            **SAMPLE_DESCRIPTOR,
            "canisters": {"casals_backend": CASALS_BOOTSTRAP_TEST_IDS["casals_backend"]},
        }
    )
    result = run_casals_new(
        desc,
        network="test",
        identity="deployer",
        casals_src=casals,
        force_create=True,
    )

    assert result["mode"] == "create"
    argv = mock_run.call_args.args[0]
    assert "--no-seed" in argv
    assert argv[argv.index("-e") + 1] == "ic"
    assert not any(str(arg).endswith(".ids.json") for arg in argv)


@patch("gaas.casals_cli.canister_missing_on_ic", return_value=True)
@patch("gaas.casals_cli.subprocess.run")
def test_run_casals_new_discards_dead_bootstrap_pin(
    mock_run: MagicMock,
    mock_missing: MagicMock,
    tmp_path: Path,
) -> None:
    casals = _make_casals_checkout(tmp_path)
    dead_backend = "2bzyp-7yaaa-aaaao-bbi6a-cai"
    fresh_backend = "qthgp-3yaaa-aaaae-agveq-cai"
    stdout = json.dumps(
        {
            "ok": True,
            "mode": "create",
            "canisters": {
                "casals_backend": fresh_backend,
                "casals_frontend": CASALS_BOOTSTRAP_TEST_IDS["casals_frontend"],
                "ic_file_registry": CASALS_BOOTSTRAP_TEST_IDS["casals_file_registry"],
                "ic_file_registry_frontend": CASALS_BOOTSTRAP_TEST_IDS[
                    "casals_file_registry_frontend"
                ],
            },
            "seeded": False,
        }
    )
    mock_run.return_value = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=stdout,
        stderr="",
    )

    desc = Descriptor.model_validate(
        {
            **SAMPLE_DESCRIPTOR,
            "canisters": {"casals_backend": dead_backend},
        }
    )
    result = run_casals_new(
        desc,
        network="ic",
        identity="deployer",
        casals_src=casals,
        yes=True,
    )

    assert result["mode"] == "create"
    assert result["healed_bootstrap_pins"] == [
        {"name": "casals_backend", "dead_id": dead_backend}
    ]
    assert "casals_backend" not in desc.canisters or desc.canisters["casals_backend"] == fresh_backend
    assert desc.canisters["casals_backend"] == fresh_backend
    argv = mock_run.call_args.args[0]
    assert not any(str(arg).endswith(".ids.json") for arg in argv)
    mock_missing.assert_called_once_with(dead_backend, "ic", identity="deployer")


@patch("gaas.casals_cli.subprocess.run")
def test_run_casals_new_force_create_rejects_upgrade(
    mock_run: MagicMock, tmp_path: Path
) -> None:
    casals = _make_casals_checkout(tmp_path)
    mock_run.return_value = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps({"ok": True, "mode": "upgrade", "canisters": {}}),
        stderr="",
    )
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    with pytest.raises(RuntimeError, match="fresh create"):
        run_casals_new(
            desc,
            network="ic",
            identity=None,
            casals_src=casals,
            force_create=True,
        )


@patch("gaas.casals_cli.subprocess.run")
def test_run_casals_new_raises_on_nonzero_exit(mock_run: MagicMock, tmp_path: Path) -> None:
    casals = _make_casals_checkout(tmp_path)
    mock_run.return_value = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="",
        stderr='{"ok": false, "error": "make build failed"}',
    )

    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    with pytest.raises(RuntimeError, match="casals new failed"):
        run_casals_new(
            desc,
            network="local",
            identity=None,
            casals_src=casals,
        )


@patch("gaas.casals_cli.subprocess.run")
def test_run_casals_sheet_deploy_argv_and_canister(mock_run: MagicMock, tmp_path: Path) -> None:
    casals = _make_casals_checkout(tmp_path)
    sheet = tmp_path / "product.json"
    sheet.write_text('{"name": "realms-product"}', encoding="utf-8")
    stdout = json.dumps({"ok": True, "deployed": []})
    mock_run.return_value = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=stdout,
        stderr="",
    )

    result = run_casals_sheet_deploy(
        sheet,
        network="test",
        identity="deployer",
        casals_src=casals,
        canister="qthgp-3yaaa-aaaae-agveq-cai",
    )

    assert result["ok"] is True
    argv = mock_run.call_args.args[0]
    assert argv[0] == sys.executable
    assert str(casals / "scripts" / "casals.py") in argv
    assert "-e" in argv
    assert argv[argv.index("-e") + 1] == "ic"
    assert "--canister" in argv
    assert argv[argv.index("--canister") + 1] == "qthgp-3yaaa-aaaae-agveq-cai"
    assert "--identity" in argv
    assert argv[argv.index("--identity") + 1] == "deployer"
    assert argv.index("--identity") < argv.index("sheet")
    assert "deploy" in argv
    assert str(sheet) in argv
    assert mock_run.call_args.kwargs["cwd"] == casals


@patch("gaas.casals_cli.subprocess.run")
def test_run_casals_sheet_deploy_raises_on_failure(mock_run: MagicMock, tmp_path: Path) -> None:
    casals = _make_casals_checkout(tmp_path)
    mock_run.return_value = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="",
        stderr='{"ok": false, "error": "deploy_sheet failed"}',
    )

    with pytest.raises(RuntimeError, match="casals sheet deploy failed"):
        run_casals_sheet_deploy(
            {"name": "realms-product"},
            network="ic",
            identity=None,
            casals_src=casals,
            canister="qthgp-3yaaa-aaaae-agveq-cai",
        )
