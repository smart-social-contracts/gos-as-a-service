#!/usr/bin/env python3
"""Create an Alpha invitation code in the registry and email it to the applicant.

    python3 scripts/invite.py applicant@example.org --dry-run
    .cto/secrets.sh run python3 scripts/invite.py applicant@example.org \\
        --identity prod-session-31oct

The code is stored on-chain as a sha256 hash only. The registry's controller is
the GaaS multisig, so the hash goes in through a multisig proposal (threshold 1:
the proposal executes as soon as the operator proposes it). See
docs/INVITATIONS.md.

Environment (never printed):
  REGISTRY_BACKEND, GAAS_MULTISIG   canister ids, from `casals export`
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import smtplib
import subprocess
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage

SENDER = "contact@realmsgos.org"
SECONDS_PER_DAY = 86400
REQUIRED_ENV = ("REGISTRY_BACKEND", "GAAS_MULTISIG")
REQUIRED_SMTP_ENV = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD")


def new_code() -> str:
    return secrets.token_hex(16).upper()


def hash_code(code: str) -> str:
    """Same hash as the registry's api.invitations.hash_code."""
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def expiry_seconds(days: int, now: float) -> int:
    return int(now + days * SECONDS_PER_DAY)


def invitation_payload(code: str, credits: int, expires_at: int) -> str:
    """The text argument of create_invitation_codes."""
    entry = {"hash": hash_code(code), "credits": credits, "expires_at": expires_at}
    return json.dumps([entry])


def propose_args(registry: str, payload: str) -> str:
    """Candid for multisig.propose(CallCanister create_invitation_codes, null)."""
    arg_json = json.dumps(payload)[1:-1]
    return (
        f'(variant {{ CallCanister = record {{ canister = principal "{registry}"; '
        f'method = "create_invitation_codes"; arg_json = "{arg_json}" }} }}, null)'
    )


def icp_call(args, canister: str, method: str, candid_args: str, *flags) -> str:
    cmd = ["icp", "canister", "call", canister, method, candid_args, *flags]
    cmd += ["-n", args.network, "--identity", args.identity]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise SystemExit(f"{method} failed: {result.stderr.strip()[-400:]}")
    return result.stdout.strip()


def proposal_id(propose_output: str) -> int:
    """propose answers with the new proposal's id, e.g. ``(7 : nat)``."""
    found = re.search(r"\(\s*([\d_]+)\s*:\s*nat\s*\)", propose_output)
    if not found:
        raise SystemExit(f"propose returned no proposal id: {propose_output[-400:]}")
    return int(found.group(1).replace("_", ""))


def check_executed(proposal_output: str) -> None:
    """Fail unless the proposal executed and the registry's reply says success.

    propose returns the id even when the action fails, and the multisig counts
    any text reply as executed, so the registry's own reply (the proposal's
    ``result``) is what says whether the code was stored.
    """
    status = re.search(r"status = variant \{ (\w+) \}", proposal_output)
    if not status or status.group(1) != "executed":
        raise SystemExit(f"proposal did not execute: {proposal_output[-400:]}")
    result = re.search(r'result = opt "((?:[^"\\]|\\.)*)"', proposal_output)
    try:
        reply = json.loads(json.loads(f'"{result.group(1)}"'))
    except (AttributeError, ValueError):
        raise SystemExit(f"proposal has no readable registry reply: {proposal_output[-400:]}")
    if not isinstance(reply, dict) or reply.get("success") is not True:
        raise SystemExit(f"registry refused the invitation: {reply}")


def create_code(args, registry: str, multisig: str, payload: str) -> None:
    proposed = icp_call(args, multisig, "propose", propose_args(registry, payload))
    proposal = icp_call(
        args, multisig, "get_proposal", f"({proposal_id(proposed)} : nat)", "--query"
    )
    check_executed(proposal)


def compose_email(to: str, code: str, credits: int, expires_at: int, portal: str):
    until = datetime.fromtimestamp(expires_at, timezone.utc).strftime("%d %B %Y")
    message = EmailMessage()
    message["From"] = SENDER
    message["To"] = to
    message["Subject"] = "Your gos.earth invitation code"
    message.set_content(
        "Hello,\n\n"
        "Your request to try gos.earth (Alpha) is approved.\n\n"
        f"Invitation code: {code}\n\n"
        f"1. Open {portal}/deploy-gos and sign in with Internet Identity.\n"
        f"2. Enter the code. {credits} free credits are added to your account.\n\n"
        f"The code works once and expires on {until}.\n\n"
        "Realms GOS\n"
    )
    return message


def send_email(message: EmailMessage) -> None:
    host, port = os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
    with server:
        if port != 465:
            server.starttls()
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        server.send_message(message)


def missing_env(names) -> list:
    return [name for name in names if not os.environ.get(name)]


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("email", help="the applicant's address")
    parser.add_argument("--days", type=int, default=30, help="days the code is valid")
    parser.add_argument("--credits", type=int, default=50, help="credits it grants")
    parser.add_argument("--identity", help="icp identity that signs the proposal")
    parser.add_argument("--network", default="ic", help="icp network (default ic)")
    parser.add_argument("--portal", default="https://gos.earth", help="portal URL")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the email and the proposal; create and send nothing",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    code = new_code()
    expires_at = expiry_seconds(args.days, time.time())
    payload = invitation_payload(code, args.credits, expires_at)
    message = compose_email(args.email, code, args.credits, expires_at, args.portal)

    if args.dry_run:
        print(f"Would propose create_invitation_codes: {payload}\n")
        print(message)
        return

    missing = missing_env(REQUIRED_ENV + REQUIRED_SMTP_ENV)
    if missing:
        raise SystemExit(f"set these environment variables: {', '.join(missing)}")
    if not args.identity:
        raise SystemExit("pass --identity, the icp identity that signs the proposal")

    create_code(
        args, os.environ["REGISTRY_BACKEND"], os.environ["GAAS_MULTISIG"], payload
    )
    try:
        send_email(message)
    except (OSError, smtplib.SMTPException) as error:
        # The code already exists on-chain; losing it would waste an invitation.
        print(
            f"Email failed ({error}). Send {code} to {args.email} by hand.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"Invitation sent to {args.email}, valid {args.days} days.")


if __name__ == "__main__":
    main()
