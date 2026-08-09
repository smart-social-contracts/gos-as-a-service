"""Tests for run-scoped logging helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gaas.runlog import (
    CommandError,
    RunLog,
    format_duration,
    run_subprocess,
    start_run_log,
    stop_run_log,
    tail_text,
)


def test_tail_text_limits_lines() -> None:
    text = "\n".join(f"line {index}" for index in range(100))
    tail = tail_text(text, 40)
    assert tail.startswith("line 60")
    assert tail.endswith("line 99")
    assert len(tail.splitlines()) == 40


def test_format_duration() -> None:
    assert format_duration(12.4) == "12s"
    assert format_duration(75.0) == "1m15s"


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

    captured = capsys.readouterr().out
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

    captured = capsys.readouterr().out
    assert "building realm_registry_frontend" in captured
    assert "done (" in captured
    log.close()


def test_start_run_log_path_convention(tmp_path: Path) -> None:
    stop_run_log()
    log = start_run_log("test-env", log_dir=tmp_path)
    assert log.path.parent == tmp_path
    assert log.path.name.startswith("test-env-")
    assert log.path.suffix == ".log"
    stop_run_log()


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
