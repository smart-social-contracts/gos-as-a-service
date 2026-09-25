"""Single-use registry vouchers: checksum in, plaintext never stored."""

import hashlib

from realm_registry_backend.api.vouchers import (
    checksum_for_code,
    issue_voucher,
    redeem_voucher,
    redemptions_for,
)
from realm_registry_backend.core.models import UserCredits, Voucher

CALLER = "kpbof-gom7k-b4gsj-sfmka-fvbac-y72nv-sb7f2-b4v4e-4557j-erlzq-2qe"


def _clear():
    for row in list(Voucher.instances()):
        row.delete()
    for row in list(UserCredits.instances()):
        row.delete()


def test_issue_and_redeem_once():
    _clear()
    code = "beta50"
    checksum = checksum_for_code(code)
    assert checksum == "sha256:" + hashlib.sha256(b"BETA50").hexdigest()

    denied = issue_voucher(checksum, 50, is_controller=False)
    assert denied["success"] is False

    issued = issue_voucher(checksum, 50, is_controller=True)
    assert issued["success"] is True
    assert Voucher[checksum].redeemer == ""

    again = issue_voucher(checksum, 50, is_controller=True)
    assert again["success"] is False

    first = redeem_voucher("  beta50  ", CALLER)
    assert first["success"] is True
    assert first["credits"] == 50
    assert first["balance"] == 50
    assert UserCredits[CALLER].balance == 50

    second = redeem_voucher("BETA50", "other-principal")
    assert second["success"] is False
    assert second["error"] == "already used"
    assert UserCredits[CALLER].balance == 50

    unknown = redeem_voucher("NOPE", CALLER)
    assert unknown["error"] == "invalid voucher code"

    history = redemptions_for(CALLER)
    assert history == [{"credits": 50, "redeemed_at": history[0]["redeemed_at"]}]
    assert "checksum" not in history[0]
    assert "BETA50" not in str(history)


def test_credits_bounds():
    _clear()
    checksum = checksum_for_code("ONE")
    assert issue_voucher(checksum, 0, is_controller=True)["success"] is False
    assert issue_voucher(checksum, 10001, is_controller=True)["success"] is False
    assert issue_voucher("not-a-hash", 10, is_controller=True)["success"] is False
    assert issue_voucher(checksum, 10000, is_controller=True)["success"] is True
