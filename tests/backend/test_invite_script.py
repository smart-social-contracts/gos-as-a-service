"""scripts/invite.py: the code it stores must be the code it emails."""

import importlib.util
import json
import smtplib
from pathlib import Path
from types import SimpleNamespace

import pytest

from realm_registry_backend.api.invitations import hash_code as registry_hash_code

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "invite.py"
spec = importlib.util.spec_from_file_location("invite", SCRIPT)
invite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(invite)

ENV = {
    "REGISTRY_BACKEND": "registry-id",
    "GAAS_MULTISIG": "multisig-id",
    "SMTP_HOST": "smtp.example.org",
    "SMTP_PORT": "587",
    "SMTP_USER": "contact@realmsgos.org",
    "SMTP_PASSWORD": "hunter2",
}


@pytest.fixture
def live(monkeypatch):
    """Real-run environment with the icp call and the mail server recorded."""
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    events = []

    def fake_run(cmd, **kwargs):
        events.append(("icp", cmd))
        return SimpleNamespace(returncode=0, stdout="(variant { Ok })", stderr="")

    def fake_send(message):
        events.append(("mail", message))

    monkeypatch.setattr(invite.subprocess, "run", fake_run)
    monkeypatch.setattr(invite, "send_email", fake_send)
    return events


def test_hash_matches_the_registry():
    assert invite.hash_code(" ABC123 ") == registry_hash_code("ABC123")


def test_payload_carries_hash_credits_and_expiry():
    payload = json.loads(invite.invitation_payload("ABC123", 50, 1_800_000_000))
    assert payload == [
        {
            "hash": registry_hash_code("ABC123"),
            "credits": 50,
            "expires_at": 1_800_000_000,
        }
    ]


def test_expiry_is_days_from_now():
    assert invite.expiry_seconds(30, 1000.0) == 1000 + 30 * 86400


def test_proposal_argument_is_candid_with_the_payload_escaped():
    payload = invite.invitation_payload("ABC123", 50, 1_800_000_000)
    args = invite.propose_args("registry-id", payload)
    assert 'canister = principal "registry-id"' in args
    assert 'method = "create_invitation_codes"' in args
    assert '\\"hash\\"' in args
    assert args.endswith(", null)")


def test_email_has_the_code_sender_and_expiry():
    message = invite.compose_email(
        "a@example.org", "ABC123", 50, 1_800_000_000, "https://gos.earth"
    )
    assert message["From"] == "contact@realmsgos.org"
    assert message["To"] == "a@example.org"
    body = message.get_content()
    assert "ABC123" in body
    assert "50 free credits" in body
    assert "https://gos.earth/deploy-gos" in body
    assert "15 January 2027" in body


def test_dry_run_neither_proposes_nor_sends(live, capsys):
    invite.main(["a@example.org", "--dry-run"])
    assert live == []
    out = capsys.readouterr().out
    assert "create_invitation_codes" in out
    assert "To: a@example.org" in out


def test_real_run_proposes_then_emails_the_same_code(live):
    invite.main(["a@example.org", "--identity", "operator"])
    (kind_a, cmd), (kind_b, message) = live
    assert (kind_a, kind_b) == ("icp", "mail")
    assert cmd[:5] == ["icp", "canister", "call", "multisig-id", "propose"]
    assert cmd[-4:] == ["-n", "ic", "--identity", "operator"]
    code = message.get_content().split("Invitation code: ")[1].split()[0]
    assert registry_hash_code(code) in cmd[5].replace("\\", "")


def test_failed_proposal_sends_no_email(live, monkeypatch):
    def failing_run(cmd, **kwargs):
        return SimpleNamespace(
            returncode=0, stdout='(variant { Err = "no" })', stderr=""
        )

    monkeypatch.setattr(invite.subprocess, "run", failing_run)
    with pytest.raises(SystemExit):
        invite.main(["a@example.org", "--identity", "operator"])
    assert live == []


def test_failed_email_reports_the_code_without_the_password(live, monkeypatch, capsys):
    def failing_send(message):
        raise smtplib.SMTPException("refused")

    monkeypatch.setattr(invite, "send_email", failing_send)
    with pytest.raises(SystemExit):
        invite.main(["a@example.org", "--identity", "operator"])
    err = capsys.readouterr().err
    assert "by hand" in err
    assert ENV["SMTP_PASSWORD"] not in err


def test_missing_settings_are_named_before_anything_runs(live, monkeypatch):
    monkeypatch.delenv("SMTP_PASSWORD")
    with pytest.raises(SystemExit, match="SMTP_PASSWORD"):
        invite.main(["a@example.org", "--identity", "operator"])
    assert live == []


def test_real_run_needs_an_identity(live):
    with pytest.raises(SystemExit, match="--identity"):
        invite.main(["a@example.org"])
    assert live == []
