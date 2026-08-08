"""Tests for seed key namespace mapping."""

from __future__ import annotations

from gaas.descriptor import Descriptor
from tests.conftest import SAMPLE_DESCRIPTOR


def test_seed_namespace_keys() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    entry = desc.gos[0]
    version = entry.version.lstrip("v")
    backend_ns = f"wasm/{entry.artifacts.backend_wasm_key}/{version}"
    frontend_ns = f"frontend/{entry.artifacts.frontend_wasm_key}/{version}"
    assert backend_ns == "wasm/realm-backend/0.3.1"
    assert frontend_ns == "frontend/realm-assets/0.3.1"
