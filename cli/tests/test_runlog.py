"""Tests for run-scoped logging helpers."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gaas.runlog import (
    CommandError,
    RunLog,
    format_cmd_for_log,
    format_duration,
    inject_log_timestamp,
    resolve_log_path,
    resolve_output_file_path,
    run_subprocess,
    stamp_log_text,
    start_run_log,
    stop_run_log,
    tail_text,
)


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    return _ANSI_RE.sub("", text)


def test_tail_text_limits_lines() -> None:
    text = "\n".join(f"line {index}" for index in range(100))
    tail = tail_text(text, 40)
    assert tail.startswith("line 60")
    assert tail.endswith("line 99")
    assert len(tail.splitlines()) == 40


def test_format_duration() -> None:
    assert format_duration(12.4) == "12s"
    assert format_duration(75.0) == "1m15s"


def test_stamp_log_text_prefixes_non_empty_lines() -> None:
    with patch("gaas.runlog.format_line_timestamp", return_value="15:04:05"):
        stamped, at_start = stamp_log_text("hello\n\nworld", True)
    assert stamped == "15:04:05 hello\n\n15:04:05 world"
    assert at_start is False


def test_run_log_write_prefixes_timestamp(tmp_path: Path) -> None:
    log_path = tmp_path / "stamped.log"
    log = RunLog(log_path)
    with patch("gaas.runlog.format_line_timestamp", return_value="12:00:00"):
        log.write("phase start")
        log.log_output("build ok\n")
    log.close()
    content = log_path.read_text(encoding="utf-8")
    assert content == "12:00:00 phase start\n12:00:00 build ok\n"


def test_run_log_writes_subprocess_output(tmp_path: Path) -> None:
    log_path = tmp_path / "test.log"
    log = RunLog(log_path)
    with patch("gaas.runlog.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="build ok\n",
            stderr="warning: chunk\n",
        )
        log.run(["npm", "run", "build"], cwd=tmp_path, label="npm build")

    content = log_path.read_text(encoding="utf-8")
    assert "$ npm run build" in content
    assert "build ok" in content
    assert "warning: chunk" in content
    log.close()


def test_run_log_failure_prints_tail(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "fail.log"
    log = RunLog(log_path)
    noisy = "\n".join(f"line {index}" for index in range(50))
    with patch("gaas.runlog.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=noisy,
            stderr="",
        )
        with pytest.raises(CommandError):
            log.run(["npm", "run", "build"], label="npm build")

    captured = _plain(capsys.readouterr().out)
    assert "npm build failed" in captured
    assert "line 49" in captured
    assert "line 0" not in captured
    log.close()


def test_run_step_prints_one_liner(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "step.log"
    log = RunLog(log_path)
    with patch("gaas.runlog.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        log.run_step("building realm_registry_frontend", ["npm", "run", "build"])

    captured = _plain(capsys.readouterr().out)
    assert "building realm_registry_frontend" in captured
    assert "done (" in captured
    log.close()


def test_inject_log_timestamp_skips_already_stamped(tmp_path: Path) -> None:
    stamped = tmp_path / "gaas-new_20260831_075800.log"
    assert inject_log_timestamp(stamped, "20260831_120000") == stamped
    plain = tmp_path / "gaas-new.log"
    assert inject_log_timestamp(plain, "20260831_075800").name == "gaas-new_20260831_075800.log"


def test_resolve_log_path_directory(tmp_path: Path) -> None:
    dest = tmp_path / "logs"
    dest.mkdir()
    path = resolve_log_path("demo", log_file=dest, ts="20260831_075800")
    assert path == dest / "gaas-new-demo_20260831_075800.log"


def test_resolve_output_file_path_default(tmp_path: Path) -> None:
    path = resolve_output_file_path("demo", log_dir=tmp_path, ts="20260831_075800")
    assert path == tmp_path / "gaas-config-demo_20260831_075800.json"


def test_resolve_output_file_path_stamps_file(tmp_path: Path) -> None:
    path = resolve_output_file_path(
        "demo", output_file=tmp_path / "demo-gaas.json", ts="20260831_075800"
    )
    assert path == tmp_path / "demo-gaas_20260831_075800.json"


def test_start_run_log_path_convention(tmp_path: Path) -> None:
    stop_run_log()
    log = start_run_log("test-env", log_dir=tmp_path)
    try:
        assert log.path.parent == tmp_path
        assert log.path.name.startswith("gaas-new-test-env_")
        assert log.path.suffix == ".log"
        assert re.search(r"_\d{8}_\d{6}\.log$", log.path.name)
    finally:
        stop_run_log()


def test_start_run_log_explicit_log_file(tmp_path: Path) -> None:
    stop_run_log()
    target = tmp_path / "nested" / "gaas-new.log"
    log = start_run_log("demo", log_file=target)
    try:
        assert log.path.parent == target.parent
        assert log.path.name.startswith("gaas-new_")
        assert re.search(r"_\d{8}_\d{6}\.log$", log.path.name)
        assert log.path.is_file()
        text = log.path.read_text(encoding="utf-8")
        assert "=== gaas run demo started" in text
        assert f"log_file={log.path}" in text
    finally:
        stop_run_log()


def test_run_log_tees_console_output(tmp_path: Path, capsys) -> None:
    stop_run_log()
    target = tmp_path / "tee.log"
    log = start_run_log("tee-env", log_file=target)
    try:
        print("phase title on console")
        log_path = log.path
    finally:
        stop_run_log()
    captured = capsys.readouterr().out
    assert "phase title on console" in captured
    log_text = log_path.read_text(encoding="utf-8")
    assert "phase title on console" in log_text
    assert re.search(r"^\d{2}:\d{2}:\d{2} phase title on console$", log_text, re.M)
    assert re.search(r"_\d{8}_\d{6}\.log$", log_path.name)


def test_gaas_new_help_has_log_file() -> None:
    from typer.testing import CliRunner

    from gaas.main import app

    result = CliRunner().invoke(app, ["new", "--help"])
    assert result.exit_code == 0
    plain = _plain(result.output)
    assert "--log-file" in plain
    assert "--output-file" in plain
    assert "YYYYMMDD_HHMMSS" in plain
    assert "gaas-config-" in plain


def test_run_subprocess_without_active_log_uses_subprocess() -> None:
    stop_run_log()
    with patch("gaas.runlog.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        run_subprocess(["echo", "hi"], check=True)
    mock_run.assert_called_once()


def test_run_subprocess_with_active_log_routes_to_file(tmp_path: Path) -> None:
    stop_run_log()
    log = start_run_log("route-test", log_dir=tmp_path)
    try:
        with patch("gaas.runlog.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="routed\n",
                stderr="",
            )
            run_subprocess(["npm", "ci"], check=True)
        assert "routed" in log.path.read_text(encoding="utf-8")
    finally:
        stop_run_log()


def test_format_cmd_for_log_omits_chunk_payload() -> None:
    payload = "A" * 8000
    cmd = [
        "dfx",
        "canister",
        "call",
        "7gyjo-wiaaa-aaaah-av2nq-cai",
        "store_file_chunk",
        (
            '{"namespace": "frontend/realm-assets/main", '
            '"path": "_app/immutable/nodes/14.CM93TY9N.js", '
            '"chunk_index": 9, "total_chunks": 17, '
            f'"data_b64": "{payload}", '
            '"content_type": "application/javascript"}'
        ),
    ]
    text = format_cmd_for_log(cmd)
    assert payload not in text
    assert "<omitted>" in text
    assert "_app/immutable/nodes/14.CM93TY9N.js" in text
    assert "chunk_index" in text

    candid = (
        '("'
        '{\\"namespace\\": \\"frontend/realm-assets/main\\", '
        '\\"path\\": \\"_app/immutable/nodes/14.CM93TY9N.js\\", '
        '\\"chunk_index\\": 9, \\"total_chunks\\": 17, '
        f'\\"data_b64\\": \\"{payload}\\", '
        '\\"content_type\\": \\"application/javascript\\"'
        '}")'
    )
    candid_text = format_cmd_for_log(["dfx", "canister", "call", candid])
    assert payload not in candid_text
    assert "<omitted>" in candid_text
    assert "14.CM93TY9N.js" in candid_text


def test_run_log_command_redacts_payload(tmp_path: Path) -> None:
    log_path = tmp_path / "payload.log"
    log = RunLog(log_path)
    blob = "B" * 4000
    log.log_command(["dfx", "call", f'{{"data_b64": "{blob}"}}'])
    log.close()
    content = log_path.read_text(encoding="utf-8")
    assert blob not in content
    assert "<omitted>" in content
    assert "$ dfx call" in content
