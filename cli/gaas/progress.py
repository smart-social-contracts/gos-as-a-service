"""Console progress for long seed/upload work."""

from __future__ import annotations

from rich.console import Console

PROGRESS_EVERY_PCT = 5

_console = Console()


class ByteProgress:
    """Print ``label: N%`` when the percent crosses a ``PROGRESS_EVERY_PCT`` step."""

    def __init__(self, label: str, total: int, *, console: Console | None = None) -> None:
        self.label = label
        self.total = max(int(total), 0)
        self.done = 0
        self._last_pct = -1
        self._console = console or _console
        self._emit(0)

    @property
    def pct(self) -> int:
        if self.total <= 0:
            return 100
        return min(100, self.done * 100 // self.total)

    def add(self, n: int) -> None:
        if n < 0:
            return
        self.done = min(self.done + n, self.total) if self.total else self.done + n
        self._maybe_emit()

    def finish(self) -> None:
        if self.total:
            self.done = self.total
        self._emit(100)

    def _maybe_emit(self) -> None:
        pct = self.pct
        if self._last_pct < 0:
            self._emit(pct)
            return
        if pct >= 100 and self._last_pct < 100:
            self._emit(100)
            return
        if pct // PROGRESS_EVERY_PCT > self._last_pct // PROGRESS_EVERY_PCT:
            self._emit(pct)

    def _emit(self, pct: int) -> None:
        if pct == self._last_pct:
            return
        self._last_pct = pct
        self._console.print(f"  {self.label}: {pct}%")
