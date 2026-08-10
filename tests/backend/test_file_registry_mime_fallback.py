"""file_registry list_files MIME fallback (realms#292)."""

import importlib.util
import sys
from pathlib import Path

# Load main.py without pulling the full canister runtime.
_main_path = Path(__file__).resolve().parents[2] / "src" / "file_registry" / "main.py"
_spec = importlib.util.spec_from_file_location("file_registry_main", _main_path)
_main = importlib.util.module_from_spec(_spec)
sys.modules["file_registry_main"] = _main
_spec.loader.exec_module(_main)


def test_effective_list_content_type_guesses_svg_when_octet_stream():
    assert (
        _main._effective_list_content_type("images/logo.svg", "application/octet-stream")
        == "image/svg+xml"
    )


def test_effective_list_content_type_keeps_explicit_type():
    assert (
        _main._effective_list_content_type("app.js", "application/javascript")
        == "application/javascript"
    )
