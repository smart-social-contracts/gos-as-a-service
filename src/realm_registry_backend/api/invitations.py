"""Invitation codes: one use each; redeeming one activates the caller and credits them.

The canister stores sha256 hashes only, never the code.
"""

import hashlib

from api.vouchers import MAX_CREDITS, credit_caller, is_sha256_hex
from core.models import ActivatedPrincipal, InvitationCode
from ic_python_logging import get_logger

logger = get_logger("invitations")

ANONYMOUS = "2vxsx-fae"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _is_number(value, kinds) -> bool:
    """isinstance(value, kinds), but True/False are not numbers here."""
    return isinstance(value, kinds) and not isinstance(value, bool)


def _validate_entry(entry) -> str | None:
    """Return why *entry* is not a valid {"hash","credits","expires_at"}, else None."""
    if not isinstance(entry, dict):
        return "each invitation must be an object"
    if not is_sha256_hex(str(entry.get("hash", ""))):
        return "hash must be 64 lowercase hex characters"
    credits = entry.get("credits")
    if not _is_number(credits, int) or credits < 0 or credits > MAX_CREDITS:
        return f"credits must be an integer from 0 to {MAX_CREDITS}"
    expires_at = entry.get("expires_at")
    if not _is_number(expires_at, (int, float)) or expires_at < 0:
        return "expires_at must be unix seconds, or 0 for never"
    return None


def create_invitations(entries: list, now: float) -> dict:
    """Store the new codes; hashes that already exist are skipped."""
    for entry in entries:
        problem = _validate_entry(entry)
        if problem:
            return {"Err": problem}
    created = 0
    for entry in entries:
        if InvitationCode[entry["hash"]]:
            continue
        InvitationCode(
            code_hash=entry["hash"],
            redeemed_by="",
            is_active=True,
            redeemed_at=0.0,
            created_at=now,
            credits=entry["credits"],
            expires_at=float(entry["expires_at"]),
        )
        created += 1
    logger.info(f"created {created} invitation codes")
    return {"Ok": {"created": created, "total_submitted": len(entries)}}


def redeem_invitation(code: str, caller: str, now: float) -> dict:
    """Activate *caller* with the code and add its credits, in one step."""
    if not caller or caller == ANONYMOUS:
        return {"Err": "sign in to redeem an invitation code"}
    if ActivatedPrincipal[caller]:
        return {"Ok": "Already activated"}

    code_hash = hash_code(code)
    invitation = InvitationCode[code_hash]
    if not invitation:
        return {"Err": "Invalid invitation code"}
    if invitation.redeemed_by:
        return {"Err": "This invitation code has already been used"}
    if not invitation.is_active:
        return {"Err": "Invalid invitation code"}
    if invitation.expires_at and now > invitation.expires_at:
        return {"Err": "This invitation code has expired"}

    # Spend the code before crediting, so a failure part-way can't leave a
    # code that credits again on the next redeem.
    credits = int(invitation.credits or 0)
    invitation.redeemed_by = caller
    invitation.redeemed_at = now
    invitation.is_active = False
    ActivatedPrincipal(
        principal_id=caller, invitation_code_hash=code_hash, activated_at=now
    )
    if credits:
        credit_caller(caller, credits, "Invitation")
    logger.info(
        f"principal {caller} activated with invitation {code_hash[:16]} credits={credits}"
    )
    return {"Ok": f"Account activated, {credits} credits added"}
