"""Tests for DNS record rendering."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gaas.dns import render_dns_records
from gaas.domain_reg import attempt_domain_registration, custom_domain_already_live

CANISTER_ID = "yhw3g-fyaaa-aaaas-qgorq-cai"


def test_render_dns_records() -> None:
    records = render_dns_records("test.gos.earth", CANISTER_ID)
    assert len(records) == 3

    host, txt, acme = records
    assert host.record_type == "CNAME/ALIAS"
    assert host.host == "test.gos.earth"
    assert host.value == "test.gos.earth.icp1.io"

    assert txt.record_type == "TXT"
    assert txt.host == "_canister-id.test.gos.earth"
    assert txt.value == CANISTER_ID

    assert acme.record_type == "CNAME"
    assert acme.host == "_acme-challenge.test.gos.earth"
    assert acme.value == "_acme-challenge.test.gos.earth.icp2.io"


@patch("gaas.domain_reg.requests.get")
def test_custom_domain_already_live(mock_get) -> None:
    mock_get.return_value = MagicMock(
        status_code=200, text="staging.gos.earth\n"
    )
    assert custom_domain_already_live("staging.gos.earth") is True
    mock_get.return_value = MagicMock(status_code=404, text="")
    assert custom_domain_already_live("staging.gos.earth") is False


@patch("gaas.domain_reg.register_domain")
@patch("gaas.domain_reg.custom_domain_already_live", return_value=True)
def test_attempt_domain_registration_skips_when_live(_live, mock_register) -> None:
    ok, detail = attempt_domain_registration("staging.gos.earth")
    assert ok is True
    assert "already serving" in detail
    mock_register.assert_not_called()
