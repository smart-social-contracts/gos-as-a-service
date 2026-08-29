"""scripts/stamp_namespace_approvals.sh refuses demo and only allows test/staging."""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "stamp_namespace_approvals.sh"


def test_stamp_script_refuses_demo() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "-e", "demo"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "refusing" in result.stderr
    assert "demo" in result.stderr


def test_stamp_script_rejects_unknown_environment() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "-e", "prod"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "test or staging" in result.stderr
