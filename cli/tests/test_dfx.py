"""Parsing tests for dfx output helpers."""

import json

import pytest

from gaas.dfx import (
    CANISTER_DELETE_FORBIDDEN,
    DfxError,
    canister_status,
    canister_call,
    create_canister,
    delete_canister,
    delete_dust_canister,
    forget_dead_named_canister_mappings,
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

    captured: dict = {"calls": []}

    def fake_run(args, **kwargs):
        captured["calls"].append(args)
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
    assert any("stop" in c for c in captured["calls"])
    assert captured["allow"] is True
    assert "delete" in captured["args"]
    assert "--no-withdrawal" in captured["args"]


def test_canister_status_retries_502(monkeypatch) -> None:
    from gaas import dfx

    calls = {"n": 0}

    def fake_run(args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise DfxError("Http Error: status 502 Bad Gateway", command=args, stderr="502")
        class R:
            stdout = "Status: Running\nBalance: 1 cycles\n"
            stderr = ""
        return R()

    monkeypatch.setattr(dfx, "_run", fake_run)
    monkeypatch.setattr(dfx.time, "sleep", lambda *_a, **_k: None)
    status = canister_status("abc", "ic", identity="deployer")
    assert calls["n"] == 3
    assert status.status == "running"


def test_canister_call_retries_502(monkeypatch) -> None:
    from gaas import dfx

    calls = {"n": 0}

    def fake_run(args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise DfxError("Http Error: status 502 Bad Gateway", command=args, stderr="502")
        class R:
            stdout = '("ok")\n'
            stderr = ""
        return R()

    monkeypatch.setattr(dfx, "_run", fake_run)
    monkeypatch.setattr(dfx.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(dfx, "_parse_candid_string", lambda stdout: "ok")
    assert canister_call("abc", "ping", '("x")', "ic", identity="deployer") == "ok"
    assert calls["n"] == 3


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


DEAD_REGISTRY = "el7rp-xiaaa-aaaai-ax43q-cai"
LIVE_STAGING_REGISTRY = "snqhl-daaaa-aaaan-q6n3q-cai"
NEW_REGISTRY = "uayfg-bqaaa-aaaac-bfygq-cai"


def test_forget_dead_named_canister_mappings_drops_dead_keeps_live(tmp_path):
    (tmp_path / "canister_ids.json").write_text(
        json.dumps(
            {
                "realm_registry_backend": {
                    "ic": DEAD_REGISTRY,
                    "test": DEAD_REGISTRY,
                    "staging": LIVE_STAGING_REGISTRY,
                    "demo": "rhw4p-gqaaa-aaaac-qbw7q-cai",
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "dfx.json").write_text(
        json.dumps(
            {
                "canisters": {
                    "realm_registry_backend": {
                        "remote": {
                            "id": {
                                "test": DEAD_REGISTRY,
                                "staging": LIVE_STAGING_REGISTRY,
                            }
                        }
                    }
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    local_dir = tmp_path / ".dfx" / "ic"
    local_dir.mkdir(parents=True)
    (local_dir / "canister_ids.json").write_text(
        json.dumps({"realm_registry_backend": {"ic": DEAD_REGISTRY}}, indent=2) + "\n",
        encoding="utf-8",
    )

    probed: list[str] = []

    def is_dead(cid: str) -> bool:
        probed.append(cid)
        return cid == DEAD_REGISTRY

    dropped = forget_dead_named_canister_mappings(
        "realm_registry_backend",
        "ic",
        cwd=tmp_path,
        is_dead=is_dead,
    )
    assert dropped == [DEAD_REGISTRY]
    assert LIVE_STAGING_REGISTRY not in probed

    ids = json.loads((tmp_path / "canister_ids.json").read_text(encoding="utf-8"))
    assert "ic" not in ids["realm_registry_backend"]
    assert "test" not in ids["realm_registry_backend"]
    assert ids["realm_registry_backend"]["staging"] == LIVE_STAGING_REGISTRY
    dfx_data = json.loads((tmp_path / "dfx.json").read_text(encoding="utf-8"))
    remote = dfx_data["canisters"]["realm_registry_backend"]["remote"]["id"]
    assert "test" not in remote
    assert remote["staging"] == LIVE_STAGING_REGISTRY
    local = json.loads((local_dir / "canister_ids.json").read_text(encoding="utf-8"))
    assert "realm_registry_backend" not in local


def test_create_canister_forgets_dead_ic_mapping_before_dfx(tmp_path, monkeypatch):
    from gaas import dfx

    (tmp_path / "canister_ids.json").write_text(
        json.dumps(
            {"realm_registry_backend": {"ic": DEAD_REGISTRY, "test": DEAD_REGISTRY}},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_status(cid, network, **kwargs):
        if cid == DEAD_REGISTRY:
            raise DfxError(
                "Canister not found",
                command=["dfx", "canister", "status", cid],
                stderr="IC0301",
            )
        return dfx.CanisterStatus(canister_id=cid, status="running", raw="Status: Running")

    def fake_run(command, **kwargs):
        written = json.loads((tmp_path / "canister_ids.json").read_text(encoding="utf-8"))
        assert DEAD_REGISTRY not in json.dumps(written)
        class R:
            stdout = f"Created canister with id {NEW_REGISTRY}\n"
            stderr = ""
            args = command
        return R()

    monkeypatch.setattr(dfx, "canister_status", fake_status)
    monkeypatch.setattr(dfx, "_run", fake_run)
    assert create_canister("realm_registry_backend", "ic", cwd=tmp_path) == NEW_REGISTRY


def test_create_canister_mints_via_ledger_if_named_create_returns_corpse(
    tmp_path, monkeypatch
):
    from gaas import dfx

    (tmp_path / "canister_ids.json").write_text(
        json.dumps({"realm_registry_backend": {"ic": DEAD_REGISTRY}}, indent=2) + "\n",
        encoding="utf-8",
    )

    def fake_status(cid, network, **kwargs):
        if cid == DEAD_REGISTRY:
            raise DfxError(
                "Canister not found",
                command=["dfx", "canister", "status", cid],
                stderr="The Replica returned an error: ... IC0301",
            )
        return dfx.CanisterStatus(canister_id=cid, status="running", raw="Status: Running")

    def fake_run(command, **kwargs):
        class R:
            stdout = f"{DEAD_REGISTRY}\n"
            stderr = ""
            args = command
        return R()

    monkeypatch.setattr(dfx, "canister_status", fake_status)
    monkeypatch.setattr(dfx, "_run", fake_run)
    monkeypatch.setattr(dfx, "create_canister_via_ledger", lambda *a, **k: NEW_REGISTRY)
    assert create_canister("realm_registry_backend", "ic", cwd=tmp_path) == NEW_REGISTRY


def test_parse_candid_string_plain_json_roundtrip():
    import json

    from gaas.dfx import _parse_candid_string

    payload = json.dumps({"ok": True, "items": [1, 2, 3], "note": "line\nbreak"})
    candid = payload.replace("\\", "\\\\").replace('"', '\\"')
    decoded = _parse_candid_string(f'(\n  "{candid}"\n)')
    assert json.loads(decoded) == json.loads(payload)
