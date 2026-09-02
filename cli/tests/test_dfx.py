"""Parsing tests for dfx output helpers."""

import json

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
    refund_canister_to_ledger,
    reject_canister_delete,
    _run as _real_dfx_run,
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


def test_deploy_assets_maps_extra_network_ids(tmp_path, monkeypatch):
    from gaas import dfx

    def fake_run(args, **kwargs):
        written = json.loads((tmp_path / "canister_ids.json").read_text(encoding="utf-8"))
        assert written["realm_registry_frontend"]["ic"] == "2zaor-5yaaa-aaaac-qbxaa-cai"
        assert written["realm_registry_backend"]["ic"] == "mjrky-pyaaa-aaaah-qu27a-cai"
        assert written["realm_registry_backend"]["demo"] == "mjrky-pyaaa-aaaah-qu27a-cai"

    monkeypatch.setattr(dfx, "_run", fake_run)
    (tmp_path / "canister_ids.json").write_text(
        json.dumps(
            {
                "realm_registry_backend": {
                    "demo": "mjrky-pyaaa-aaaah-qu27a-cai",
                }
            }
        ),
        encoding="utf-8",
    )
    dfx.deploy_assets_canister(
        "realm_registry_frontend",
        "2zaor-5yaaa-aaaac-qbxaa-cai",
        "ic",
        repo_root=tmp_path,
        extra_network_ids={
            "realm_registry_backend": "mjrky-pyaaa-aaaah-qu27a-cai",
            "realm_registry_frontend": "2zaor-5yaaa-aaaac-qbxaa-cai",
        },
    )
    restored = json.loads((tmp_path / "canister_ids.json").read_text(encoding="utf-8"))
    assert "ic" not in restored["realm_registry_backend"]
    assert restored["realm_registry_backend"]["demo"] == "mjrky-pyaaa-aaaah-qu27a-cai"


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


def test_add_canister_controller_is_additive(monkeypatch) -> None:
    from gaas import dfx

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = args

    monkeypatch.setattr(dfx, "_run", fake_run)
    dfx.add_canister_controller(
        "yhw3g-fyaaa-aaaas-qgorq-cai",
        "qthgp-3yaaa-aaaae-agveq-cai",
        "ic",
        identity="deployer",
    )
    args = captured["args"]
    assert "update-settings" in args
    assert "--add-controller" in args
    assert "--set-controller" not in args
    assert "qthgp-3yaaa-aaaae-agveq-cai" in args


def test_reject_canister_delete_blocks_raw_delete() -> None:
    with pytest.raises(DfxError, match="burns leftover cycles"):
        reject_canister_delete(["dfx", "canister", "delete", "abc", "--yes"])


def test_reject_canister_delete_allows_status() -> None:
    reject_canister_delete(["dfx", "canister", "status", "abc"])


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


def test_refund_canister_to_ledger_allows_delete(monkeypatch) -> None:
    from gaas import dfx

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["allow"] = kwargs.get("allow_canister_delete")

    monkeypatch.setattr(dfx, "_run", fake_run)
    refund_canister_to_ledger("abc", "ic", identity="deployer")
    assert captured["allow"] is True
    assert "delete" in captured["args"]
    assert "abc" in captured["args"]


def test_run_retries_without_run_deprecated_on_stock_dfx(monkeypatch) -> None:
    from gaas import dfx

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        if "--run-deprecated" in command:
            return type(
                "R",
                (),
                {
                    "returncode": 2,
                    "stdout": "",
                    "stderr": "error: unexpected argument '--run-deprecated' found\n",
                },
            )()
        return type(
            "R",
            (),
            {"returncode": 0, "stdout": "uayfg-bqaaa-aaaac-bfygq-cai\n", "stderr": ""},
        )()

    monkeypatch.setattr(dfx, "_run", _real_dfx_run)
    monkeypatch.setattr(dfx.subprocess, "run", fake_run)
    result = dfx._run(["dfx", "identity", "get-wallet", "--network", "ic"], check=True)
    assert [c[1] if len(c) > 1 else "" for c in calls][0] == "--run-deprecated"
    assert calls[1] == ["dfx", "identity", "get-wallet", "--network", "ic"]
    assert result.stdout.strip() == "uayfg-bqaaa-aaaac-bfygq-cai"


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
