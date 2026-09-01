"""Tests for seed/upload percent progress."""

from __future__ import annotations

from unittest.mock import MagicMock

from gaas.progress import ByteProgress, PROGRESS_EVERY_PCT


def test_byte_progress_prints_start_steps_and_finish() -> None:
    console = MagicMock()
    progress = ByteProgress("uploading frontend", 100, console=console)
    assert PROGRESS_EVERY_PCT == 5
    console.print.assert_called_with("  uploading frontend: 0%")

    progress.add(4)
    assert console.print.call_count == 1
    progress.add(1)
    console.print.assert_called_with("  uploading frontend: 5%")
    progress.add(10)
    console.print.assert_called_with("  uploading frontend: 15%")
    progress.finish()
    console.print.assert_called_with("  uploading frontend: 100%")


def test_byte_progress_skips_duplicate_percent() -> None:
    console = MagicMock()
    progress = ByteProgress("uploading wasm", 10, console=console)
    progress.add(10)
    progress.finish()
    printed = [call.args[0] for call in console.print.call_args_list]
    assert printed == [
        "  uploading wasm: 0%",
        "  uploading wasm: 100%",
    ]
