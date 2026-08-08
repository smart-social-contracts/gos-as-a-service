"""Unit tests for realm_installer.ic_assets.ensure_frame_ancestor."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from ic_assets import ensure_frame_ancestor, portal_url_to_origin

_SAMPLE = """[
    {
        "match": "**/*",
        "headers": {
            "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; script-src 'self';"
        }
    }
]"""


def test_portal_url_to_origin_strips_path():
    assert portal_url_to_origin("https://test.gos.earth/r/my-realm") == "https://test.gos.earth"


def test_adds_origin_when_frame_ancestors_is_none():
    out = ensure_frame_ancestor(_SAMPLE, "https://staging.gos.earth")
    assert "frame-ancestors https://staging.gos.earth" in out
    assert "'none'" not in out.split("frame-ancestors", 1)[1].split(";", 1)[0]


def test_idempotent_when_origin_already_present():
    patched = ensure_frame_ancestor(_SAMPLE, "https://staging.gos.earth")
    again = ensure_frame_ancestor(patched, "https://staging.gos.earth")
    assert again == patched


def test_malformed_input_returned_unchanged():
    bad = "not json at all {{"
    assert ensure_frame_ancestor(bad, "https://example.com") == bad


def test_empty_origin_returns_input():
    assert ensure_frame_ancestor(_SAMPLE, "") == _SAMPLE
