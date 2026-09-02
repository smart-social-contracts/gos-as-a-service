"""Run-scoped logging: quiet console, verbose log file."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

_LOG_TS_FMT = "%Y%m%d_%H%M%S"
_LINE_TS_FMT = "%H:%M:%S"
_STAMPED_STEM_RE = re.compile(r"_\d{8}_\d{6}$")
_TAIL_LINES = 40
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_DEFAULT_LOG_PREFIX = "gaas-new"
_DEFAULT_CONFIG_PREFIX = "gaas-config"
_MAX_LOG_ARG_CHARS = 512
_JSON_QUOTE = r'(?:\\"|")'
_DATA_B64_RE = re.compile(
    rf"(data_b64{_JSON_QUOTE}?\s*:\s*{_JSON_QUOTE})[A-Za-z0-9+/=]+({_JSON_QUOTE})"
)

_console = Console()
_active: RunLog | None = None


class CommandError(RuntimeError):
    def __init__(self, message: str, *, cmd: list[str], tail: str) -> None:
        super().__init__(message)
        self.cmd = cmd
        self.tail = tail


def format_line_timestamp() -> str:
    """UTC clock for per-line log prefixes (``HH:MM:SS``)."""
    return datetime.now(timezone.utc).strftime(_LINE_TS_FMT)


def stamp_log_text(text: str, at_line_start: bool) -> tuple[str, bool]:
    """Prefix each non-empty line with ``HH:MM:SS ``. Blank lines stay blank."""
    if not text:
        return "", at_line_start
    parts: list[str] = []
    i = 0
    length = len(text)
    while i < length:
        if at_line_start:
            if text[i] == "\n":
                parts.append("\n")
                i += 1
                continue
            parts.append(f"{format_line_timestamp()} ")
            at_line_start = False
        nl = text.find("\n", i)
        if nl == -1:
            parts.append(text[i:])
            return "".join(parts), False
        parts.append(text[i : nl + 1])
        at_line_start = True
        i = nl + 1
    return "".join(parts), at_line_start


class _TeeStream:
    """Mirror stdout/stderr into the run log (ANSI stripped) while keeping the TTY."""

    def __init__(self, primary, log: RunLog) -> None:
        self._primary = primary
        self._log = log
        self._tty_at_line_start = True

    def write(self, data) -> int:
        if isinstance(data, bytes):
            text = data.decode("utf-8", errors="replace")
        else:
            text = data if isinstance(data, str) else str(data)
        stamped_tty, self._tty_at_line_start = stamp_log_text(
            text, self._tty_at_line_start
        )
        n = self._primary.write(stamped_tty)
        stripped = _ANSI_RE.sub("", text)
        if stripped:
            self._log._write_raw(stripped)
        return n if isinstance(n, int) else len(text)

    def flush(self) -> None:
        self._primary.flush()
        self._log._file.flush()

    def isatty(self) -> bool:
        return bool(getattr(self._primary, "isatty", lambda: False)())

    def fileno(self) -> int:
        return self._primary.fileno()

    def __getattr__(self, name: str):
        return getattr(self._primary, name)


class RunLog:
    def __init__(self, path: Path, ts: str | None = None) -> None:
        self.path = path
        self.ts = ts or ""
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("a", encoding="utf-8", buffering=1)
        self._stdout_orig = None
        self._stderr_orig = None
        self._at_line_start = True

    def _write_raw(self, text: str) -> None:
        stamped, self._at_line_start = stamp_log_text(text, self._at_line_start)
        self._file.write(stamped)
        self._file.flush()

    def write(self, line: str) -> None:
        self._write_raw(line.rstrip("\n") + "\n")

    def install_tee(self) -> None:
        if self._stdout_orig is not None:
            return
        self._stdout_orig = sys.stdout
        self._stderr_orig = sys.stderr
        sys.stdout = _TeeStream(sys.stdout, self)
        sys.stderr = _TeeStream(sys.stderr, self)

    def uninstall_tee(self) -> None:
        if self._stdout_orig is None:
            return
        sys.stdout = self._stdout_orig
        sys.stderr = self._stderr_orig
        self._stdout_orig = None
        self._stderr_orig = None

    def log_command(self, cmd: list[str], *, cwd: str | Path | None = None) -> None:
        parts = [f"$ {format_cmd_for_log(cmd)}"]
        if cwd:
            parts.append(f"  (cwd={cwd})")
        self.write("\n".join(parts))

    def log_output(self, text: str) -> None:
        if not text:
            return
        if not text.endswith("\n"):
            text += "\n"
        self._write_raw(text)

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
                f"command failed: {format_cmd_for_log(cmd)}",
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
        self.uninstall_tee()
        self._file.close()


def redact_cmd_args(cmd: list[str]) -> list[str]:
    """Shorten huge argv values (candid `data_b64`, inline JSON) for logs/errors."""
    redacted: list[str] = []
    for arg in cmd:
        if "data_b64" in arg:
            arg = _DATA_B64_RE.sub(r'\1<omitted>\2', arg)
        if len(arg) <= _MAX_LOG_ARG_CHARS:
            redacted.append(arg)
            continue
        redacted.append(f"{arg[:80]}... <{len(arg)} chars omitted>")
    return redacted


def format_cmd_for_log(cmd: list[str]) -> str:
    return " ".join(redact_cmd_args(cmd))


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


def _safe_env_name(env_name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in env_name) or "run"


def default_log_dir() -> Path:
    """``<git-root>/logs`` when cwd is inside a checkout, otherwise ``./logs``."""
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ".git").exists():
            return candidate / "logs"
    return here / "logs"


def _is_log_directory(path: Path) -> bool:
    if path.exists():
        return path.is_dir()
    return path.suffix == ""


def dated_artifact_name(prefix: str, env_name: str, ts: str, suffix: str) -> str:
    ext = suffix if suffix.startswith(".") else f".{suffix}"
    return f"{prefix}-{_safe_env_name(env_name)}_{ts}{ext}"


def dated_log_name(prefix: str, env_name: str, ts: str) -> str:
    return dated_artifact_name(prefix, env_name, ts, ".log")


def inject_log_timestamp(path: Path, ts: str) -> Path:
    """Insert ``_YYYYMMDD_HHMMSS`` before the suffix unless already stamped."""
    stem = path.stem
    if _STAMPED_STEM_RE.search(stem):
        return path
    suffix = path.suffix or ".log"
    return path.with_name(f"{stem}_{ts}{suffix}")


def resolve_log_path(
    env_name: str,
    *,
    log_dir: Path | None = None,
    log_file: str | Path | None = None,
    prefix: str = _DEFAULT_LOG_PREFIX,
    ts: str | None = None,
) -> Path:
    """Default: ``<repo>/logs/gaas-new-<env>_YYYYMMDD_HHMMSS.log``.

    ``--log-file`` to a directory (or a path with no suffix) writes a dated
    file there. A file path gets ``_YYYYMMDD_HHMMSS`` inserted before the
    extension unless it is already stamped.
    """
    stamp = ts or datetime.now(timezone.utc).strftime(_LOG_TS_FMT)
    if log_file:
        path = Path(log_file).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if _is_log_directory(path):
            return path / dated_log_name(prefix, env_name, stamp)
        return inject_log_timestamp(path, stamp)
    base = log_dir or default_log_dir()
    return base / dated_log_name(prefix, env_name, stamp)


def resolve_output_file_path(
    env_name: str,
    *,
    log_dir: Path | None = None,
    output_file: str | Path | None = None,
    ts: str | None = None,
) -> Path:
    """Default: ``<repo>/logs/gaas-config-<env>_YYYYMMDD_HHMMSS.json``.

    ``--output-file`` to a directory writes a dated file there. A file path
    gets ``_YYYYMMDD_HHMMSS`` inserted before the extension unless it is
    already stamped.
    """
    stamp = ts or datetime.now(timezone.utc).strftime(_LOG_TS_FMT)
    if output_file:
        path = Path(output_file).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if _is_log_directory(path):
            return path / dated_artifact_name(
                _DEFAULT_CONFIG_PREFIX, env_name, stamp, ".json"
            )
        return inject_log_timestamp(path, stamp)
    base = log_dir or default_log_dir()
    return base / dated_artifact_name(
        _DEFAULT_CONFIG_PREFIX, env_name, stamp, ".json"
    )


def start_run_log(
    env_name: str,
    *,
    log_dir: Path | None = None,
    log_file: str | Path | None = None,
) -> RunLog:
    """Create and activate a per-invocation run log.

    Default path is ``<repo>/logs/gaas-new-<env>_YYYYMMDD_HHMMSS.log``.
    Console output is teed into the same file.
    """
    global _active
    ts = datetime.now(timezone.utc).strftime(_LOG_TS_FMT)
    path = resolve_log_path(env_name, log_dir=log_dir, log_file=log_file, ts=ts)
    log = RunLog(path, ts=ts)
    log.write(f"=== gaas run {env_name} started {ts} UTC ===")
    log.write(f"log_file={path}")
    log.install_tee()
    _active = log
    return log


def get_run_log() -> RunLog | None:
    return _active


def print_path(label: str, path: Path, *, console: Console | None = None) -> None:
    """Print an absolute path without wrapping so terminals don't hyphenate it."""
    (console or _console).print(
        f"{label} {path}",
        overflow="ignore",
        crop=False,
        no_wrap=True,
    )


def print_log_path(*, console: Console | None = None) -> None:
    if _active is not None:
        print_path("Full logs:", _active.path, console=console)


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
        if label:
            return log.run_step(label, cmd, cwd=cwd, env=env, check=check)
        return log.run(cmd, cwd=cwd, env=env, check=check, label=label)
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        check=check,
    )
