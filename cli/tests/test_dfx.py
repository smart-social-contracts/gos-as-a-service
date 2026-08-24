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


def test_parse_created_canister_id_prefers_created_line():
    import subprocess

    from gaas.dfx import _parse_created_canister_id

    subnet = "o3ow2-2ipam-6fcjo-3j5vt-fzbge-2g7my-5fz2m-p7o5s-daa"
    created = "aaaaa-aa"
    # Use a realistic canister id so the regex can match either line.
    created = "qthgp-3yaaa-aaaae-agveq-cai"
    result = subprocess.CompletedProcess(
        args=["dfx", "canister", "create"],
        returncode=0,
        stdout=(
            f"Creating canister on subnet {subnet}\n"
            f"Created canister {created}\n"
        ),
        stderr="",
    )
    assert _parse_created_canister_id(result) == created


def test_drop_local_canister_id_removes_network_mapping(tmp_path, monkeypatch):
    import json

    from gaas.dfx import drop_local_canister_id, local_canister_id

    ids_path = tmp_path / "canister_ids.json"
    ids_path.write_text(
        json.dumps(
            {
                "realm_installer": {
                    "ic": "hznxf-fqaaa-aaaae-ag2ua-cai",
                    "staging": "fksuf-niaaa-aaaae-ag22q-cai",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert local_canister_id("realm_installer", "ic") == "hznxf-fqaaa-aaaae-ag2ua-cai"
    drop_local_canister_id("realm_installer", "ic")
    assert local_canister_id("realm_installer", "ic") is None
    leftover = json.loads(ids_path.read_text(encoding="utf-8"))
    assert leftover["realm_installer"]["staging"] == "fksuf-niaaa-aaaae-ag22q-cai"


def test_create_canister_drops_stale_mapping_and_verifies(tmp_path, monkeypatch):
    import json
    import subprocess

    from gaas import dfx

    ids_path = tmp_path / "canister_ids.json"
    stale = "gudtl-kyaaa-aaaae-ag2tq-cai"
    fresh = "qthgp-3yaaa-aaaae-agveq-cai"
    ids_path.write_text(
        json.dumps({"realm_registry_backend": {"ic": stale}}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exists = {stale: False, fresh: True}

    def fake_exists(canister_id, network, *, identity=None):
        del network, identity
        return exists[canister_id]

    def fake_run(args, **kwargs):
        del kwargs
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=f"Created canister {fresh}\n",
            stderr="",
        )

    monkeypatch.setattr(dfx, "canister_exists", fake_exists)
    monkeypatch.setattr(dfx, "_run", fake_run)

    got = dfx.create_canister("realm_registry_backend", "ic", identity="deployer")
    assert got == fresh
    assert "ic" not in json.loads(ids_path.read_text(encoding="utf-8")).get(
        "realm_registry_backend", {}
    )


def test_create_canister_raises_if_parsed_id_missing(monkeypatch):
    import subprocess

    from gaas import dfx

    fresh = "qthgp-3yaaa-aaaae-agveq-cai"

    monkeypatch.setattr(dfx, "local_canister_id", lambda *a, **k: None)
    monkeypatch.setattr(dfx, "canister_exists", lambda *a, **k: False)
    monkeypatch.setattr(dfx, "drop_local_canister_id", lambda *a, **k: None)
    monkeypatch.setattr(
        dfx,
        "_run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=f"Created canister {fresh}\n",
            stderr="",
        ),
    )

    with pytest.raises(dfx.DfxError, match="does not exist on-chain"):
        dfx.create_canister("realm_installer", "ic")


def test_create_canister_via_ledger_retired_on_ic():
    from gaas.dfx import DfxError, create_canister_via_ledger

    with pytest.raises(DfxError, match="retired"):
        create_canister_via_ledger("ic", identity="deployer")
