"""Single-use credit vouchers. The canister stores sha256 checksums only."""

import hashlib
import re
import time

from core.models import CreditTransaction, UserCredits, Voucher
from ic_python_logging import get_logger

logger = get_logger("vouchers")

_CHECKSUM_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
MIN_CREDITS = 1
MAX_CREDITS = 10_000
INVALID = "invalid voucher code"
USED = "already used"


def normalize_code(code: str) -> str:
    return (code or "").strip().upper()


def checksum_for_code(code: str) -> str:
    normalized = normalize_code(code)
    if not normalized:
        raise ValueError("empty voucher code")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def parse_checksum(value: str) -> str:
    text = (value or "").strip().lower()
    if not text.startswith("sha256:"):
        text = f"sha256:{text}"
    if not _CHECKSUM_RE.match(text):
        raise ValueError("checksum must be sha256: and 64 hex characters")
    return text


def issue_voucher(checksum: str, credits: int, *, is_controller: bool) -> dict:
    if not is_controller:
        return {"success": False, "error": "Only controllers can issue vouchers"}
    try:
        amount = int(credits)
    except (TypeError, ValueError):
        return {"success": False, "error": "credits must be an integer"}
    if amount < MIN_CREDITS or amount > MAX_CREDITS:
        return {"success": False, "error": f"credits must be from {MIN_CREDITS} to {MAX_CREDITS}"}
    try:
        stored = parse_checksum(checksum)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    if Voucher[stored]:
        return {"success": False, "error": "voucher already issued"}
    Voucher(checksum=stored, credits=amount, redeemer="", redeemed_at=0.0)
    logger.info(f"issued voucher {stored[:16]} credits={amount}")
    return {"success": True, "checksum": stored, "credits": amount}


def _credit_caller(principal_id: str, amount: int) -> dict:
    uc = UserCredits[principal_id]
    if uc:
        uc.balance = (uc.balance or 0) + amount
        uc.total_purchased = (uc.total_purchased or 0) + amount
    else:
        uc = UserCredits(
            principal_id=principal_id, balance=amount,
            total_purchased=amount, total_spent=0,
        )
    CreditTransaction(
        id=f"tx_v_{hashlib.sha256(f'{principal_id}:{time.time_ns()}'.encode()).hexdigest()[:16]}",
        principal_id=principal_id,
        amount=amount,
        transaction_type="topup",
        description="Voucher",
        stripe_session_id="",
        timestamp=time.time(),
    )
    return uc.to_dict()


def redeem_voucher(code: str, caller: str) -> dict:
    caller = (caller or "").strip()
    if not caller or caller == "2vxsx-fae":
        return {"success": False, "error": "sign in to redeem a voucher"}
    try:
        stored = checksum_for_code(code)
    except ValueError:
        return {"success": False, "error": INVALID}
    voucher = Voucher[stored]
    if not voucher:
        return {"success": False, "error": INVALID}
    if (voucher.redeemer or "").strip():
        return {"success": False, "error": USED}
    amount = int(voucher.credits or 0)
    if amount < MIN_CREDITS:
        return {"success": False, "error": INVALID}
    credits = _credit_caller(caller, amount)
    voucher.redeemer = caller
    voucher.redeemed_at = time.time()
    logger.info(f"redeemed voucher {stored[:16]} by {caller}")
    return {
        "success": True,
        "message": f"Successfully redeemed {amount} credits",
        "credits": amount,
        "balance": credits["balance"],
        "total_purchased": credits["total_purchased"],
        "total_spent": credits["total_spent"],
    }


def redemptions_for(caller: str) -> list:
    caller = (caller or "").strip()
    if not caller or caller == "2vxsx-fae":
        return []
    rows = []
    for voucher in Voucher.instances():
        if (voucher.redeemer or "") != caller:
            continue
        rows.append({
            "credits": int(voucher.credits or 0),
            "redeemed_at": float(voucher.redeemed_at or 0),
        })
    rows.sort(key=lambda row: row["redeemed_at"], reverse=True)
    return rows
