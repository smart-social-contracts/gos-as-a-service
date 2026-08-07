import time
import uuid

from core.models import CreditTransaction, DeploymentCreditHold, UserCredits
from ic_python_logging import get_logger

logger = get_logger("credits")


def get_user_credits(principal_id: str) -> dict:
    try:
        uc = UserCredits[principal_id]
        if uc:
            return {"success": True, "credits": uc.to_dict()}
        return {"success": True, "credits": {
            "principal_id": principal_id, "balance": 0,
            "total_purchased": 0, "total_spent": 0,
        }}
    except Exception as e:
        return {"success": False, "error": str(e)}


def add_user_credits(principal_id: str, amount: int,
                     stripe_session_id: str = "", description: str = "Credit top-up") -> dict:
    if amount <= 0:
        return {"success": False, "error": "Amount must be positive"}
    if amount > 1000:
        return {"success": False, "error": "Amount cannot exceed 1000"}
    try:
        uc = UserCredits[principal_id]
        if uc:
            uc.balance = (uc.balance or 0) + amount
            uc.total_purchased = (uc.total_purchased or 0) + amount
        else:
            uc = UserCredits(principal_id=principal_id, balance=amount,
                             total_purchased=amount, total_spent=0)
        CreditTransaction(
            id=f"tx_{uuid.uuid4().hex[:16]}", principal_id=principal_id,
            amount=amount, transaction_type="topup", description=description,
            stripe_session_id=stripe_session_id, timestamp=time.time(),
        )
        return {"success": True, "credits": uc.to_dict()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def deduct_user_credits(principal_id: str, amount: int,
                        description: str = "Credit spend") -> dict:
    if amount <= 0:
        return {"success": False, "error": "Amount must be positive"}
    try:
        uc = UserCredits[principal_id]
        if not uc:
            return {"success": False, "error": "User has no credits"}
        bal = uc.balance or 0
        if bal < amount:
            return {"success": False, "error": f"Insufficient credits: {bal} < {amount}"}
        uc.balance = bal - amount
        uc.total_spent = (uc.total_spent or 0) + amount
        CreditTransaction(
            id=f"tx_{uuid.uuid4().hex[:16]}", principal_id=principal_id,
            amount=-amount, transaction_type="spend", description=description,
            stripe_session_id="", timestamp=time.time(),
        )
        return {"success": True, "credits": uc.to_dict()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_billing_status() -> dict:
    try:
        users = list(UserCredits.instances())
        return {"success": True, "billing": {
            "users_count": len(users),
            "total_balance": sum(u.balance or 0 for u in users),
            "total_purchased": sum(u.total_purchased or 0 for u in users),
            "total_spent": sum(u.total_spent or 0 for u in users),
        }}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_user_transactions(principal_id: str, limit: int = 50) -> dict:
    try:
        txs = [tx for tx in CreditTransaction.all() if tx.principal_id == principal_id]
        txs.sort(key=lambda x: x.timestamp or 0, reverse=True)
        return {"success": True, "transactions": [t.to_dict() for t in txs[:limit]]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_deployment_hold(principal_id: str, job_id: str, amount: int,
                           description: str = "Deployment hold") -> dict:
    if amount <= 0 or not job_id:
        return {"success": False, "error": "Invalid amount or job_id"}
    try:
        existing = DeploymentCreditHold[job_id]
        if existing:
            return {"success": existing.status in ("held", "captured"),
                    "hold": existing.to_dict(), "idempotent": True}
        uc = UserCredits[principal_id]
        if not uc:
            return {"success": False, "error": "User has no credits"}
        bal = uc.balance or 0
        if bal < amount:
            return {"success": False, "error": f"Insufficient credits: {bal} < {amount}"}
        uc.balance = bal - amount
        hold = DeploymentCreditHold(
            job_id=job_id, principal_id=principal_id, amount=amount,
            status="held", reason=description, created_at=time.time(), settled_at=0.0,
        )
        CreditTransaction(
            id=f"tx_{uuid.uuid4().hex[:16]}", principal_id=principal_id,
            amount=-amount, transaction_type="hold",
            description=f"{description} (job={job_id})",
            stripe_session_id="", timestamp=time.time(),
        )
        return {"success": True, "hold": hold.to_dict()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def capture_deployment_hold(job_id: str, description: str = "Deployment captured") -> dict:
    if not job_id:
        return {"success": False, "error": "job_id required"}
    try:
        hold = DeploymentCreditHold[job_id]
        if not hold:
            return {"success": False, "error": f"Hold not found: {job_id}"}
        if hold.status == "captured":
            return {"success": True, "hold": hold.to_dict(), "idempotent": True}
        if hold.status == "released":
            return {"success": False, "error": "Hold already released"}
        uc = UserCredits[hold.principal_id]
        if not uc:
            uc = UserCredits(principal_id=hold.principal_id, balance=0,
                             total_purchased=0, total_spent=0)
        uc.total_spent = (uc.total_spent or 0) + (hold.amount or 0)
        hold.status = "captured"
        hold.reason = description
        hold.settled_at = time.time()
        return {"success": True, "hold": hold.to_dict()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def release_deployment_hold(job_id: str, description: str = "Deployment released") -> dict:
    if not job_id:
        return {"success": False, "error": "job_id required"}
    try:
        hold = DeploymentCreditHold[job_id]
        if not hold:
            return {"success": False, "error": f"Hold not found: {job_id}"}
        if hold.status == "released":
            return {"success": True, "hold": hold.to_dict(), "idempotent": True}
        if hold.status == "captured":
            return {"success": False, "error": "Hold already captured"}
        uc = UserCredits[hold.principal_id]
        if uc:
            uc.balance = (uc.balance or 0) + (hold.amount or 0)
        else:
            uc = UserCredits(principal_id=hold.principal_id, balance=hold.amount or 0,
                             total_purchased=0, total_spent=0)
        hold.status = "released"
        hold.reason = description
        hold.settled_at = time.time()
        return {"success": True, "hold": hold.to_dict()}
    except Exception as e:
        return {"success": False, "error": str(e)}
