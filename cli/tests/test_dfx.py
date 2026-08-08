"""Parsing tests for dfx output helpers."""

from gaas.dfx import parse_controllers, parse_cycles_balance, parse_module_hash


def test_parse_controllers_principal_ending_in_digits():
    raw = (
        "Canister status call result for yhw3g-fyaaa-aaaas-qgorq-cai.\n"
        "Status: Running\n"
        "Controllers: ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae "
        "cpbhu-5iaaa-aaaad-aalta-cai qthgp-3yaaa-aaaae-agveq-cai\n"
        "Memory allocation: 0 Bytes\n"
    )
    controllers = parse_controllers(raw)
    assert controllers == (
        "ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae",
        "cpbhu-5iaaa-aaaad-aalta-cai",
        "qthgp-3yaaa-aaaae-agveq-cai",
    )


def test_parse_controllers_empty():
    assert parse_controllers("Status: Running\n") == ()


def test_parse_module_hash_hex():
    raw = "Status: Running\nModule hash: 0xabc123\n"
    assert parse_module_hash(raw) == "0xabc123"


def test_parse_module_hash_none():
    assert parse_module_hash("Module hash: none\n") is None


def test_parse_cycles_balance_trillion_format():
    assert parse_cycles_balance("0.281 TC (trillion cycles).\n") == 281_000_000_000
    assert parse_cycles_balance("3.10 TC (trillion cycles)") == 3_100_000_000_000


def test_parse_cycles_balance_raw_format():
    assert parse_cycles_balance("3_072_815_616 cycles") == 3_072_815_616
    assert parse_cycles_balance("9,000,000,000,000 cycles") == 9_000_000_000_000


def test_parse_cycles_balance_unparseable():
    assert parse_cycles_balance("no balance here") is None


def test_deploy_assets_retries_transient_ic0536(tmp_path, monkeypatch):
    from gaas import dfx

    calls = {"n": 0}

    def fake_run(args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise dfx.DfxError(
                "dfx command failed",
                command=args,
                stderr="Failed to list assets: error code Some(\"IC0536\")",
            )
        return None

    monkeypatch.setattr(dfx, "_run", fake_run)
    monkeypatch.setattr(dfx.time, "sleep", lambda _s: None)
    (tmp_path / "canister_ids.json").write_text("{}", encoding="utf-8")
    dfx.deploy_assets_canister("casals_frontend", "qic2k-baaaa-aaaae-agvga-cai", "ic", repo_root=tmp_path)
    assert calls["n"] == 2


def test_deploy_assets_does_not_retry_permanent_errors(tmp_path, monkeypatch):
    import pytest

    from gaas import dfx

    def fake_run(args, **kwargs):
        raise dfx.DfxError("dfx command failed", command=args, stderr="Insufficient funds")

    monkeypatch.setattr(dfx, "_run", fake_run)
    (tmp_path / "canister_ids.json").write_text("{}", encoding="utf-8")
    with pytest.raises(dfx.DfxError):
        dfx.deploy_assets_canister("casals_frontend", "qic2k-baaaa-aaaae-agvga-cai", "ic", repo_root=tmp_path)


def test_update_canister_settings_passes_controllers(monkeypatch) -> None:
    from gaas import dfx

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = args

    monkeypatch.setattr(dfx, "_run", fake_run)
    dfx.update_canister_settings(
        "yhw3g-fyaaa-aaaas-qgorq-cai",
        ["multisig-id", "deployer-id"],
        "ic",
        identity="deployer",
    )
    args = captured["args"]
    assert "update-settings" in args
    assert args.count("--set-controller") == 2
    assert "multisig-id" in args
    assert "deployer-id" in args

