"""Tests for Casals conductor seed helpers."""

from __future__ import annotations

from gaas import conductor_seed
from gaas.conductor_seed import platform_sheet


def test_platform_sheet_has_infra_and_deployments() -> None:
    sheet = platform_sheet()
    names = [sec["name"] for sec in sheet["sections"]]
    assert names == ["Infra", "Deployments"]
    infra = sheet["sections"][0]
    assert infra["stands"][0]["name"] == "governance"
    assert infra["stands"][0]["canisters"][0]["name"] == "multisig"
    assert sheet["sections"][1]["stands"] == []


def test_ensure_deployments_commander_grants_installer(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        conductor_seed,
        "_casals_call",
        lambda _cid, method, payload, _net, **_: calls.append((method, payload))
        or {"ok": True},
    )
    conductor_seed.ensure_deployments_commander(
        "qthgp-3yaaa-aaaae-agveq-cai", "fltjm-tyaaa-aaaap-qunhq-cai", "ic"
    )
    assert calls == [
        (
            "set_commander",
            {
                "section": "Deployments",
                "commander_principal": "fltjm-tyaaa-aaaap-qunhq-cai",
                "permissions": conductor_seed.DEPLOYMENTS_COMMANDER_PERMISSIONS,
            },
        )
    ]
    perms = calls[0][1]["permissions"]
    for required in (
        "stand.create",
        "canister.create",
        "canister.deploy",
        "commander.assign",
        "orchestration.baton.create",
        "orchestration.baton.hand_off",
        "orchestration.managed_upgrade.run",
    ):
        assert required in perms
