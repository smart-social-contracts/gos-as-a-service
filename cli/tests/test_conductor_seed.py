"""Tests for Casals conductor seed helpers."""

from __future__ import annotations

from gaas.conductor_seed import platform_sheet


def test_platform_sheet_has_infra_and_deployments() -> None:
    sheet = platform_sheet()
    names = [sec["name"] for sec in sheet["sections"]]
    assert names == ["Infra", "Deployments"]
    infra = sheet["sections"][0]
    assert infra["stands"][0]["name"] == "governance"
    assert infra["stands"][0]["canisters"][0]["name"] == "multisig"
    assert sheet["sections"][1]["stands"] == []
