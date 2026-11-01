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


def proposal_output(status="executed", reply='{"success": true, "created": 1}'):
    """What `get_proposal` prints: the registry's reply is the proposal's result."""
    result = reply.replace("\\", "\\\\").replace('"', '\\"')
    return (
        f"(opt record {{ id = 7 : nat; status = variant {{ {status} }}; "
        f'result = opt "{result}"; }})'
    )


def icp_replies(proposal):
    """A fake `icp canister call`: propose answers with the id, get_proposal with *proposal*."""

    def fake_run(cmd, **kwargs):
        stdout = "(7 : nat)" if cmd[4] == "propose" else proposal
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    return fake_run


class FakeMailServer:
    """Records the login (on opening) and the sent message; never touches the network."""

    def __init__(self, events):
        self.events = events
        events.append(("login", None))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def send_message(self, message):
        self.events.append(("mail", message))


@pytest.fixture
def live(monkeypatch):
    """Real-run environment with the icp call and the mail server recorded."""
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    events = []
    reply = icp_replies(proposal_output())

    def fake_run(cmd, **kwargs):
        events.append(("icp", cmd))
        return reply(cmd)

    monkeypatch.setattr(invite.subprocess, "run", fake_run)
    monkeypatch.setattr(invite, "open_mail_server", lambda: FakeMailServer(events))
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


@pytest.mark.parametrize(
    "portal, host",
    [("https://gos.earth", "gos.earth"), ("https://staging.gos.earth", "staging.gos.earth")],
)
def test_subject_names_the_portal_host(portal, host):
    message = invite.compose_email("a@example.org", "ABC123", 50, 1_800_000_000, portal)
    assert message["Subject"] == f"Your {host} invitation code"
    assert f"try {host} (Alpha)" in message.get_content()


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


def test_dry_run_prints_a_placeholder_not_a_real_code(live, monkeypatch, capsys):
    monkeypatch.setattr(invite, "new_code", lambda: pytest.fail("minted a real code"))
    invite.main(["a@example.org", "--dry-run"])
    assert f"Invitation code: {invite.DRY_RUN_CODE}" in capsys.readouterr().out


def test_failed_login_creates_no_code(live, monkeypatch, capsys):
    def refuse_login():
        raise SystemExit("SMTP login failed, no code was created: refused")

    monkeypatch.setattr(invite, "open_mail_server", refuse_login)
    with pytest.raises(SystemExit, match="no code was created"):
        invite.main(["a@example.org", "--identity", "operator"])
    assert live == []
    assert capsys.readouterr().err == ""


def test_smtp_login_error_becomes_a_fatal_exit(monkeypatch):
    class RefusingServer:
        def __init__(self, *args, **kwargs):
            pass

        def starttls(self):
            pass

        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(invite.smtplib, "SMTP", RefusingServer)
    with pytest.raises(SystemExit, match="no code was created") as refused:
        invite.open_mail_server()
    assert ENV["SMTP_PASSWORD"] not in str(refused.value)


def test_real_run_proposes_then_emails_the_same_code(live):
    invite.main(["a@example.org", "--identity", "operator"])
    (kind_0, _), (kind_a, propose), (kind_b, check), (kind_c, message) = live
    assert (kind_0, kind_a, kind_b, kind_c) == ("login", "icp", "icp", "mail")
    assert propose[:5] == ["icp", "canister", "call", "multisig-id", "propose"]
    assert propose[-4:] == ["-n", "ic", "--identity", "operator"]
    assert check[:6] == ["icp", "canister", "call", "multisig-id", "get_proposal", "(7 : nat)"]
    code = message.get_content().split("Invitation code: ")[1].split()[0]
    assert registry_hash_code(code) in propose[5].replace("\\", "")


def test_codes_carry_at_least_128_bits():
    assert len(bytes.fromhex(invite.new_code())) >= 16


@pytest.mark.parametrize(
    "proposal",
    [
        proposal_output(status="failed", reply="empty reply"),
        proposal_output(status="pending", reply="{}"),
        proposal_output(reply='{"success": false, "error": "bad hash"}'),
        proposal_output(reply="not json"),
        "(null)",
    ],
)
def test_unexecuted_or_refused_proposal_sends_no_email(live, monkeypatch, proposal):
    monkeypatch.setattr(invite.subprocess, "run", icp_replies(proposal))
    with pytest.raises(SystemExit):
        invite.main(["a@example.org", "--identity", "operator"])
    assert "mail" not in [kind for kind, _ in live]


def test_propose_without_an_id_sends_no_email(live, monkeypatch):
    monkeypatch.setattr(
        invite.subprocess,
        "run",
        lambda cmd, **kwargs: SimpleNamespace(
            returncode=0, stdout='(variant { Err = "no" })', stderr=""
        ),
    )
    with pytest.raises(SystemExit):
        invite.main(["a@example.org", "--identity", "operator"])
    assert "mail" not in [kind for kind, _ in live]


def test_failed_email_reports_the_code_without_the_password(live, monkeypatch, capsys):
    def failing_send(self, message):
        raise smtplib.SMTPException("refused")

    monkeypatch.setattr(FakeMailServer, "send_message", failing_send)
    with pytest.raises(SystemExit):
        invite.main(["a@example.org", "--identity", "operator"])
    err = capsys.readouterr().err
    assert "by hand" in err
    assert "do not rerun" in err
    assert ENV["SMTP_PASSWORD"] not in err


def test_portal_must_be_https(live):
    with pytest.raises(SystemExit):
        invite.main(["a@example.org", "--dry-run", "--portal", "http://gos.earth"])
    assert live == []


def test_missing_settings_are_named_before_anything_runs(live, monkeypatch):
    monkeypatch.delenv("SMTP_PASSWORD")
    with pytest.raises(SystemExit, match="SMTP_PASSWORD"):
        invite.main(["a@example.org", "--identity", "operator"])
    assert live == []


def test_real_run_needs_an_identity(live):
    with pytest.raises(SystemExit, match="--identity"):
        invite.main(["a@example.org"])
    assert live == []
