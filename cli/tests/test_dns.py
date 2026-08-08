"""Tests for DNS record rendering."""

from __future__ import annotations

from gaas.dns import render_dns_records

CANISTER_ID = "yhw3g-fyaaa-aaaas-qgorq-cai"


def test_render_dns_records() -> None:
    records = render_dns_records("test.gos.earth", CANISTER_ID)
    assert len(records) == 3

    host, txt, acme = records
    assert host.record_type == "CNAME/ALIAS"
    assert host.host == "test.gos.earth"
    assert host.value == "icp1.io"

    assert txt.record_type == "TXT"
    assert txt.host == "_canister-id.test.gos.earth"
    assert txt.value == CANISTER_ID

    assert acme.record_type == "CNAME"
    assert acme.host == "_acme-challenge.test.gos.earth"
    assert acme.value == "_acme-challenge.test.gos.earth.icp1.io"
