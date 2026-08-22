"""Parsing tests for dfx output helpers."""

import pytest

from gaas.dfx import (
    CANISTER_DELETE_FORBIDDEN,
    DfxError,
    delete_canister,
    delete_dust_canister,
    get_wallet,
    parse_controllers,
    parse_cycles_balance,
    parse_module_hash,
    recover_canister_cycles_to_ledger,
    reject_canister_delete,
)


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


def test_parse_canister_cycles_balance_from_status():
    from gaas.dfx import parse_canister_cycles_balance

    raw_tc = (
        "Canister status call result for yhw3g-fyaaa-aaaas-qgorq-cai.\n"
        "Status: Running\n"
        "Balance: 0.604 TC (trillion cycles)\n"
    )
    assert parse_canister_cycles_balance(raw_tc) == 604_000_000_000

    raw_cycles = (
        "Status: Running\n"
        "Balance: 3_072_815_616 cycles\n"
    )
    assert parse_canister_cycles_balance(raw_cycles) == 3_072_815_616


def test_deploy_assets_passes_yes_flag(tmp_path, monkeypatch):
    from gaas import dfx

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = args

    monkeypatch.setattr(dfx, "_run", fake_run)
    (tmp_path / "canister_ids.json").write_text("{}", encoding="utf-8")
    dfx.deploy_assets_canister(
        "casals_frontend",
        "qic2k-baaaa-aaaae-agvga-cai",
        "ic",
        repo_root=tmp_path,
        yes=True,
    )
    assert "--yes" in captured["args"]


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


def test_prepare_dfx_args_skips_run_deprecated_when_stock_dfx(monkeypatch) -> None:
    from gaas import dfx

    monkeypatch.setattr(dfx, "_DFX_ACCEPTS_RUN_DEPRECATED", False)
    args = dfx._prepare_dfx_args(["dfx", "identity", "get-principal", "--identity", "deployer"])
    assert args[0:2] == ["dfx", "identity"]
    assert "--run-deprecated" not in args


def test_prepare_dfx_args_injects_run_deprecated_when_wrapper_dfx(monkeypatch) -> None:
    from gaas import dfx

    monkeypatch.setattr(dfx, "_DFX_ACCEPTS_RUN_DEPRECATED", True)
    args = dfx._prepare_dfx_args(["dfx", "identity", "get-principal"])
    assert args[0:2] == ["dfx", "--run-deprecated"]


def test_reject_canister_delete_blocks_raw_delete() -> None:
    with pytest.raises(DfxError, match="burns leftover cycles"):
        reject_canister_delete(["dfx", "canister", "delete", "abc", "--yes"])


def test_reject_canister_delete_allows_status() -> None:
    reject_canister_delete(["dfx", "canister", "status", "abc"])


def test_reject_canister_delete_allows_icp_recover() -> None:
    reject_canister_delete(["icp", "canister", "delete", "abc", "-n", "ic"])


def test_delete_canister_always_raises() -> None:
    with pytest.raises(DfxError, match=CANISTER_DELETE_FORBIDDEN):
        delete_canister()


def test_delete_dust_canister_refuses_when_fat(monkeypatch) -> None:
    from gaas import dfx

    monkeypatch.setattr(
        dfx,
        "canister_status",
        lambda *_a, **_k: dfx.CanisterStatus(
            canister_id="abc",
            status="running",
            raw="Balance: 1_000_000_000_000 cycles",
        ),
    )

    with pytest.raises(DfxError, match="refusing canister delete"):
        delete_dust_canister("abc", "ic", identity="deployer", max_cycles=500_000_000_000)


def test_delete_dust_canister_allows_dust(monkeypatch) -> None:
    from gaas import dfx

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["allow"] = kwargs.get("allow_canister_delete")

    monkeypatch.setattr(
        dfx,
        "canister_status",
        lambda *_a, **_k: dfx.CanisterStatus(
            canister_id="abc",
            status="running",
            raw="Balance: 100_000_000_000 cycles",
        ),
    )
    monkeypatch.setattr(dfx, "_run", fake_run)
    delete_dust_canister("abc", "ic", identity="deployer", max_cycles=500_000_000_000)
    assert captured["allow"] is True
    assert "delete" in captured["args"]


def test_recover_canister_cycles_to_ledger(monkeypatch) -> None:
    from gaas import dfx

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["allow"] = kwargs.get("allow_canister_delete")
        return type("R", (), {"stdout": "deleted\n", "stderr": "", "returncode": 0})()

    monkeypatch.setattr(
        dfx,
        "canister_status",
        lambda *a, **k: type(
            "S",
            (),
            {
                "canister_id": "abc",
                "status": "running",
                "raw": "Balance: 12_000_000_000_000 cycles",
            },
        )(),
    )
    monkeypatch.setattr(dfx, "parse_canister_cycles_balance", lambda raw: 12_000_000_000_000)
    monkeypatch.setattr(dfx, "_run", fake_run)
    recovered = recover_canister_cycles_to_ledger("abc", "ic", identity="deployer")
    assert recovered == 12_000_000_000_000
    assert captured["allow"] is True
    assert captured["args"][0] == "icp"
    assert captured["args"][1:4] == ["canister", "delete", "abc"]
    assert "--no-recover-cycles" not in captured["args"]


def test_get_wallet(monkeypatch) -> None:
    from gaas import dfx

    monkeypatch.setattr(
        dfx,
        "_run",
        lambda args, **kwargs: type(
            "R", (), {"stdout": "wallet-principal\n", "stderr": "", "returncode": 0}
        )(),
    )
    assert get_wallet("ic", identity="deployer") == "wallet-principal"


def test_parse_candid_string_preserves_json_escaped_backslash_before_n():
    """Regression: gaas seed crashed with JSONDecodeError on Casals payloads
    containing a JSON-escaped backslash followed by 'n' (e.g. "C:\\\\new"),
    because sequential unescape replaces ate the quadrupled backslash."""
    import json

    from gaas.dfx import _parse_candid_string

    payload = json.dumps({"path": "C:\\new", "quote": 'say "hi"'})
    candid = payload.replace("\\", "\\\\").replace('"', '\\"')
    raw = f'("{candid}")'
    decoded = _parse_candid_string(raw)
    assert json.loads(decoded) == {"path": "C:\\new", "quote": 'say "hi"'}


def test_parse_candid_string_plain_json_roundtrip():
    import json

    from gaas.dfx import _parse_candid_string

    payload = json.dumps({"ok": True, "items": [1, 2, 3], "note": "line\nbreak"})
    candid = payload.replace("\\", "\\\\").replace('"', '\\"')
    decoded = _parse_candid_string(f'(\n  "{candid}"\n)')
    assert json.loads(decoded) == json.loads(payload)
