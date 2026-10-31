"""Invitation codes: one use, optional expiry, and the credits they carry."""

from realm_registry_backend.api.invitations import (
    create_invitations,
    hash_code,
    redeem_invitation,
)
from realm_registry_backend.core.models import (
    ActivatedPrincipal,
    InvitationCode,
    UserCredits,
)

CALLER = "kpbof-gom7k-b4gsj-sfmka-fvbac-y72nv-sb7f2-b4v4e-4557j-erlzq-2qe"
OTHER = "rrkah-fqaaa-aaaaa-aaaaq-cai"
NOW = 1_800_000_000.0


def _clear():
    for model in (InvitationCode, ActivatedPrincipal, UserCredits):
        for row in list(model.instances()):
            row.delete()


def _invite(code, credits=50, expires_at=0):
    entry = {"hash": hash_code(code), "credits": credits, "expires_at": expires_at}
    return create_invitations([entry], NOW)


def test_redeem_activates_and_credits_once():
    _clear()
    assert _invite("ALPHA1") == {"Ok": {"created": 1, "total_submitted": 1}}

    first = redeem_invitation("  ALPHA1 ", CALLER, NOW)
    assert first == {"Ok": "Account activated, 50 credits added"}
    assert ActivatedPrincipal[CALLER].invitation_code_hash == hash_code("ALPHA1")
    assert UserCredits[CALLER].balance == 50

    second = redeem_invitation("ALPHA1", OTHER, NOW)
    assert second == {"Err": "This invitation code has already been used"}
    assert ActivatedPrincipal[OTHER] is None
    assert UserCredits[OTHER] is None


def test_unknown_and_revoked_codes_are_invalid():
    _clear()
    assert redeem_invitation("NOPE", CALLER, NOW) == {"Err": "Invalid invitation code"}

    _invite("REVOKED")
    InvitationCode[hash_code("REVOKED")].is_active = False
    assert redeem_invitation("REVOKED", CALLER, NOW) == {
        "Err": "Invalid invitation code"
    }
    assert UserCredits[CALLER] is None


def test_expired_code_is_refused_and_stays_unused():
    _clear()
    _invite("OLD", expires_at=NOW - 1)
    assert redeem_invitation("OLD", CALLER, NOW) == {
        "Err": "This invitation code has expired"
    }
    assert ActivatedPrincipal[CALLER] is None
    assert InvitationCode[hash_code("OLD")].redeemed_by == ""

    _invite("FRESH", expires_at=NOW + 3600)
    assert "Ok" in redeem_invitation("FRESH", CALLER, NOW)


def test_activated_principal_keeps_the_second_code():
    _clear()
    _invite("ONE")
    _invite("TWO")
    redeem_invitation("ONE", CALLER, NOW)

    assert redeem_invitation("TWO", CALLER, NOW) == {"Ok": "Already activated"}
    assert InvitationCode[hash_code("TWO")].redeemed_by == ""
    assert UserCredits[CALLER].balance == 50


def test_anonymous_caller_cannot_redeem():
    _clear()
    _invite("ANON")
    assert "Err" in redeem_invitation("ANON", "2vxsx-fae", NOW)
    assert InvitationCode[hash_code("ANON")].redeemed_by == ""


def test_access_only_code_adds_no_credits():
    _clear()
    _invite("ACCESS", credits=0)
    assert redeem_invitation("ACCESS", CALLER, NOW) == {
        "Ok": "Account activated, 0 credits added"
    }
    assert UserCredits[CALLER] is None


def test_create_skips_existing_hashes_and_validates_all_first():
    _clear()
    _invite("DUP")
    again = create_invitations(
        [
            {"hash": hash_code("DUP"), "credits": 50, "expires_at": 0},
            {"hash": hash_code("NEW"), "credits": 50, "expires_at": 0},
        ],
        NOW,
    )
    assert again == {"Ok": {"created": 1, "total_submitted": 2}}

    bad = create_invitations(
        [
            {"hash": hash_code("GOOD"), "credits": 50, "expires_at": 0},
            {"hash": "not-a-hash", "credits": 50, "expires_at": 0},
        ],
        NOW,
    )
    assert "Err" in bad
    assert InvitationCode[hash_code("GOOD")] is None


def test_create_rejects_bad_credits_and_expiry():
    _clear()
    digest = hash_code("X")
    for credits, expires_at in [
        (-1, 0),
        (10_001, 0),
        ("50", 0),
        (50, -5),
        (50, "never"),
    ]:
        entry = {"hash": digest, "credits": credits, "expires_at": expires_at}
        assert "Err" in create_invitations([entry], NOW), (credits, expires_at)
    assert "Err" in create_invitations(["just-a-hash"], NOW)
