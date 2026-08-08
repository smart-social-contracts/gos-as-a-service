"""Parsing tests for dfx output helpers."""

from gaas.dfx import parse_controllers, parse_cycles_balance


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


def test_parse_cycles_balance_trillion_format():
    assert parse_cycles_balance("0.281 TC (trillion cycles).\n") == 281_000_000_000
    assert parse_cycles_balance("3.10 TC (trillion cycles)") == 3_100_000_000_000


def test_parse_cycles_balance_raw_format():
    assert parse_cycles_balance("3_072_815_616 cycles") == 3_072_815_616
    assert parse_cycles_balance("9,000,000,000,000 cycles") == 9_000_000_000_000


def test_parse_cycles_balance_unparseable():
    assert parse_cycles_balance("no balance here") is None
