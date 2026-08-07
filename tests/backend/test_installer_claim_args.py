"""Unit tests for realm_installer.claim_args."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from claim_args import build_claim_slug_args


def test_legacy_manifest_five_arg_form():
    manifest = {"federation": {"slug": "my-realm"}}
    result = build_claim_slug_args("my-realm", "fe-id", "be-id", manifest)
    assert result == '("my-realm", "fe-id", "be-id", "", "")'


def test_full_gos_block_nine_arg_form():
    manifest = {
        "gos": {
            "implementation": "realms-gos",
            "version": "0.4.0",
            "ggg_conformance": "1.0",
            "loader_profile": "realms-iframe-v1",
        },
    }
    result = build_claim_slug_args("my-realm", "fe-id", "be-id", manifest)
    assert result == (
        '("my-realm", "fe-id", "be-id", "", "", '
        'opt "realms-gos", opt "0.4.0", opt "1.0", opt "realms-iframe-v1")'
    )


def test_partial_gos_emits_null_for_missing_keys():
    manifest = {"gos": {"implementation": "realms-gos"}}
    result = build_claim_slug_args("slug", "fe", "be", manifest)
    assert result == (
        '("slug", "fe", "be", "", "", opt "realms-gos", null, null, null)'
    )


def test_quote_escaping():
    manifest = {"gos": {"implementation": 'say "hello\\world"'}}
    result = build_claim_slug_args("slug", "fe", "be", manifest)
    assert result == (
        '("slug", "fe", "be", "", "", '
        'opt "say \\"hello\\\\world\\"", null, null, null)'
    )
