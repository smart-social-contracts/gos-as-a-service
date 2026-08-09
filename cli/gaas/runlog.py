"""Run-scoped logging: quiet console, verbose log file."""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

_DEFAULT_LOG_DIR = Path.home() / ".gaas" / "logs"
_TAIL_LINES = 40

_console = Console()
_active: RunLog | None = None


class CommandError(RuntimeError):
    def __init__(self, message: str, *, cmd: list[str], tail: str) -> None:
        super().__init__(message)
        self.cmd = cmd
        self.tail = tail


class RunLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("a", encoding="utf-8", buffering=1)

    def write(self, line: str) -> None:
        self._file.write(line.rstrip("\n") + "\n")
        self._file.flush()

    def log_command(self, cmd: list[str], *, cwd: str | Path | None = None) -> None:
        parts = [f"$ {' '.join(cmd)}"]
        if cwd:
            parts.append(f"  (cwd={cwd})")
        self.write("\n".join(parts))

    def log_output(self, text: str) -> None:
        if not text:
            return
        self._file.write(text)
        if not text.endswith("\n"):
            self._file.write("\n")
        self._file.flush()

    def run(
        self,
        cmd: list[str],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        check: bool = True,
        label: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self.log_command(cmd, cwd=cwd)
        merged_env = {**os.environ, **(env or {})}
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=merged_env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.stdout:
            self.log_output(result.stdout)
        if result.stderr:
            self.log_output(result.stderr)
        if check and result.returncode != 0:
            combined = (result.stdout or "") + (result.stderr or "")
            tail = tail_text(combined, _TAIL_LINES)
            name = label or " ".join(cmd[:3])
            _console.print(f"[red]{name} failed (exit {result.returncode})[/red]")
            if tail:
                _console.print("[dim]--- last lines from log ---[/dim]")
                _console.print(tail)
            raise CommandError(
                f"command failed: {' '.join(cmd)}",
                cmd=cmd,
                tail=tail,
            )
        return result

    def run_step(
        self,
        label: str,
        cmd: list[str],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        start = time.monotonic()
        _console.print(f"  {label}...", end=" ")
        try:
            result = self.run(
                cmd,
                cwd=cwd,
                env=env,
                check=check,
                label=label,
            )
        except CommandError:
            _console.print("failed")
            raise
        elapsed = time.monotonic() - start
        _console.print(f"done ({format_duration(elapsed)})")
        return result

    def close(self) -> None:
        self._file.close()


def format_duration(seconds: float) -> str:
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    return f"{total // 60}m{total % 60}s"


def tail_text(text: str, lines: int) -> str:
    parts = text.splitlines()
    if len(parts) <= lines:
        return "\n".join(parts)
    return "\n".join(parts[-lines:])


def start_run_log(env_name: str, *, log_dir: Path | None = None) -> RunLog:
    """Create and activate a per-invocation run log under ~/.gaas/logs/."""
    global _active
    base = log_dir or _DEFAULT_LOG_DIR
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in env_name)
    path = base / f"{safe_name}-{ts}.log"
    log = RunLog(path)
    log.write(f"=== gaas run {env_name} started {ts} UTC ===")
    _active = log
    return log


def get_run_log() -> RunLog | None:
    return _active


def print_log_path(*, console: Console | None = None) -> None:
    if _active is not None:
        (console or _console).print(f"Full logs: {_active.path}")


def stop_run_log() -> None:
    global _active
    if _active is not None:
        _active.close()
        _active = None


def run_subprocess(
    cmd: list[str],
    *,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    label: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess; route output to the active run log when present."""
    log = get_run_log()
    if log is not None:
        return log.run(cmd, cwd=cwd, env=env, check=check, label=label)
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        check=check,
    )
