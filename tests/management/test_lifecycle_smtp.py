from __future__ import annotations

import smtplib
import socketserver
import threading
from contextlib import contextmanager, suppress
from email import message_from_bytes, policy
from email.message import EmailMessage
from multiprocessing import active_children
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlsplit

import pytest

from huginn.management.application.read_models.lifecycle_mail_message import (
    LifecycleMailMessage,
)
from huginn.management.config import ManagementConfig
from huginn.management.delivery.smtp_lifecycle_mail_sender import (
    SmtpLifecycleMailSender,
    _send_smtp,
)
from huginn.management.delivery.templates.reset_password import render_reset_mail
from huginn.management.delivery.templates.verify_email import (
    render_verification_mail,
)


class _SmtpHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.wfile.write(b"220 local SMTP sink\r\n")
        self.wfile.flush()
        while line := self.rfile.readline():
            command = line.decode("ascii", errors="replace").strip()
            verb = command.split(" ", 1)[0].upper()
            if verb in {"EHLO", "HELO"}:
                response = b"250 localhost\r\n"
            elif verb == "DATA":
                self.wfile.write(b"354 send message\r\n")
                self.wfile.flush()
                content = bytearray()
                while data_line := self.rfile.readline():
                    if data_line == b".\r\n":
                        break
                    content.extend(data_line)
                self.server.messages.append(bytes(content))
                response = b"250 message accepted\r\n"
            elif verb == "QUIT":
                self.wfile.write(b"221 closing connection\r\n")
                self.wfile.flush()
                return
            else:
                response = b"250 accepted\r\n"
            self.wfile.write(response)
            self.wfile.flush()


class _SmtpServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _SmtpHandler)
        self.messages: list[bytes] = []


@contextmanager
def _smtp_sink():
    server = _SmtpServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _link_from(message: EmailMessage) -> str:
    return next(
        line for line in message.get_content().splitlines() if line.startswith("http")
    )


def test_verification_template_puts_encoded_proof_in_fragment():
    message = render_verification_mail(
        recipient="ada@example.test",
        sender="no-reply@example.test",
        token="opaque_proof-123",
        web_origin="https://app.example.test",
    )

    assert message["To"] == "ada@example.test"
    assert message["From"] == "no-reply@example.test"
    assert "verify" in message["Subject"].lower()
    link = urlsplit(_link_from(message))
    assert link.path == "/verify-email"
    assert link.query == ""
    assert link.fragment == "token=opaque_proof-123"


def test_reset_template_links_to_reset_page_in_fragment():
    message = render_reset_mail(
        recipient="ada@example.test",
        sender="no-reply@example.test",
        token="reset-proof-123",
        web_origin="https://app.example.test",
    )

    link = urlsplit(_link_from(message))
    assert link.path == "/reset-password"
    assert link.query == ""
    assert link.fragment == "token=reset-proof-123"
    assert "reset" in message["Subject"].lower()


@pytest.mark.parametrize("renderer", [render_verification_mail, render_reset_mail])
@pytest.mark.parametrize(
    "recipient",
    [
        '"ada"@example.test',
        '"first.last"@example.test',
        '"first,last"@example.test',
        '"first;last"@example.test',
        "josé@example.test",
        "ada@例子.test",
    ],
)
def test_templates_accept_single_quoted_and_unicode_mailboxes(renderer, recipient):
    message = renderer(
        recipient=recipient,
        sender='"no-reply"@example.test',
        token="valid-proof",
        web_origin="https://app.example.test",
    )
    local, domain = recipient.rsplit("@", 1)
    assert message["To"].addresses[0].username == local.strip('"')
    assert message["To"].addresses[0].domain == domain
    assert len(message["To"].addresses) == 1


def test_total_smtp_deadline_terminates_sender_process(monkeypatch, caplog):
    class DelayedWriter:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

        def write(self, data):
            sleep(0.2)
            return self.wrapped.write(data)

    class SlowHandler(_SmtpHandler):
        def handle(self):
            self.wfile = DelayedWriter(self.wfile)
            with suppress(OSError):
                super().handle()

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), SlowHandler)
    server.daemon_threads = True
    server.messages = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    before = {child.pid for child in active_children()}
    monkeypatch.setattr(
        "huginn.management.delivery.smtp_lifecycle_mail_sender.MAIL_TIMEOUT_SECONDS",
        0.5,
    )
    try:
        sender = SmtpLifecycleMailSender(
            ManagementConfig(
                database_url="unused",
                web_origin="http://localhost:4173",
                smtp_host="127.0.0.1",
                smtp_port=server.server_address[1],
            )
        )
        started = monotonic()
        with pytest.raises(OSError, match="lifecycle mail transport failed"):
            sender.send(
                LifecycleMailMessage(
                    "private@example.test", "verify_email", "private-proof"
                )
            )
        elapsed = monotonic() - started
        assert elapsed < 1.5
        assert {child.pid for child in active_children()} == before
        assert (
            "private@example.test" not in caplog.text
            and "private-proof" not in caplog.text
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("renderer", (render_verification_mail, render_reset_mail))
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("recipient", "ada@example.test\r\nBcc: attacker@example.test"),
        ("recipient", "ada@example.test,attacker"),
        ("recipient", "ada@example.test,attacker@example.test"),
        ("recipient", "ada@example.test\x00"),
        ("sender", "no-reply@example.test\x7f"),
        ("sender", "no-reply@example.test\r\nBcc: attacker@example.test"),
        ("token", "proof\r\nBcc: attacker@example.test"),
        ("web_origin", "https://app.example.test\r\nBcc: attacker@example.test"),
        ("web_origin", "https://app.example.test/attacker?token=leak"),
    ),
)
def test_templates_reject_header_injection_and_non_origin_links(renderer, field, value):
    args: dict[str, Any] = {
        "recipient": "ada@example.test",
        "sender": "no-reply@example.test",
        "token": "valid-proof",
        "web_origin": "https://app.example.test",
    }
    args[field] = value

    with pytest.raises(ValueError):
        renderer(**args)


def test_sender_delivers_rendered_verification_and_reset_mail_to_local_sink(caplog):
    with _smtp_sink() as server:
        host, port = server.server_address
        config = ManagementConfig(
            database_url="unused",
            web_origin="http://localhost:4173",
            smtp_host=host,
            smtp_port=port,
            smtp_sender="no-reply@example.test",
        )
        sender = SmtpLifecycleMailSender(config)
        verification = LifecycleMailMessage(
            recipient="ada@example.test",
            purpose="verify_email",
            token="verify-proof-123",
        )
        reset = LifecycleMailMessage(
            recipient="ada@example.test",
            purpose="reset_password",
            token="reset-proof-456",
        )

        sender.send(verification)
        sender.send(reset)

        assert len(server.messages) == 2
        messages = [
            message_from_bytes(payload, policy=policy.default)
            for payload in server.messages
        ]
        links = [urlsplit(_link_from(message)) for message in messages]
        assert [link.path for link in links] == ["/verify-email", "/reset-password"]
        assert [link.fragment for link in links] == [
            "token=verify-proof-123",
            "token=reset-proof-456",
        ]
        assert all(link.query == "" for link in links)
        assert "verify-proof-123" not in caplog.text
        assert "reset-proof-456" not in caplog.text


def test_sender_rejects_missing_trusted_origin_before_transport():
    config = ManagementConfig(database_url="unused")

    with pytest.raises(ValueError, match="trusted web origin"):
        SmtpLifecycleMailSender(config)


def test_sender_requires_smtp_credentials_as_a_pair():
    config = ManagementConfig(
        database_url="unused",
        web_origin="https://app.example.test",
        smtp_username="smtp-user",
    )

    with pytest.raises(ValueError, match="configured together"):
        SmtpLifecycleMailSender(config)


def test_sender_rejects_bad_recipient_before_transport():
    config = ManagementConfig(
        database_url="unused",
        web_origin="https://app.example.test",
        smtp_host="127.0.0.1",
        smtp_port=1,
    )
    sender = SmtpLifecycleMailSender(config)

    with pytest.raises(ValueError, match="recipient"):
        sender.send(
            LifecycleMailMessage(
                recipient="ada@example.test\r\nBcc: attacker@example.test",
                purpose="verify_email",
                token="valid-proof",
            )
        )


def test_sender_rejects_unsupported_purpose_before_transport():
    config = ManagementConfig(
        database_url="unused",
        web_origin="https://app.example.test",
        smtp_host="127.0.0.1",
        smtp_port=1,
    )

    with pytest.raises(ValueError, match="purpose"):
        SmtpLifecycleMailSender(config).send(
            LifecycleMailMessage("ada@example.test", "unsupported", "valid-proof")
        )


def test_sender_uses_starttls_with_default_context_and_authentication(
    monkeypatch, caplog
):
    calls: list[tuple[str, Any]] = []

    class FakeSmtp:
        def __enter__(self):
            calls.append(("enter", None))
            return self

        def __exit__(self, *_):
            calls.append(("exit", None))

        def ehlo(self):
            calls.append(("ehlo", None))

        def starttls(self, *, context):
            calls.append(("starttls", context))

        def login(self, username, password):
            calls.append(("login", (username, password)))

        def send_message(self, message, *, from_addr, to_addrs):
            assert from_addr == "no-reply@huginn.local"
            assert to_addrs == ["ada@example.test"]
            calls.append(("send", message["Subject"]))
            return {}

    def smtp_factory(*args, **kwargs):
        calls.append(("factory", (args, kwargs)))
        return FakeSmtp()

    monkeypatch.setattr(
        "huginn.management.delivery.smtp_lifecycle_mail_sender.smtplib.SMTP",
        smtp_factory,
    )
    monkeypatch.setattr(
        "huginn.management.delivery.smtp_lifecycle_mail_sender.ssl.create_default_context",
        lambda: "default-tls-context",
    )
    config = ManagementConfig(
        database_url="unused",
        web_origin="https://app.example.test",
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_tls="starttls",
        smtp_username="smtp-user",
        smtp_password="smtp-secret",
    )

    _send_smtp(
        config, LifecycleMailMessage("ada@example.test", "verify_email", "valid-proof")
    )

    assert calls[0][0] == "factory"
    assert calls[0][1] == (
        ("smtp.example.test", 587),
        {"timeout": 30},
    )
    assert calls[1:] == [
        ("enter", None),
        ("ehlo", None),
        ("starttls", "default-tls-context"),
        ("ehlo", None),
        ("login", ("smtp-user", "smtp-secret")),
        ("send", "Verify your Huginn email address"),
        ("exit", None),
    ]
    assert "smtp-secret" not in caplog.text


def test_sender_uses_implicit_tls_and_raises_when_recipient_is_refused(monkeypatch):
    calls: list[tuple[str, Any]] = []

    class FakeSmtp:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def send_message(self, message, *, from_addr, to_addrs):
            assert from_addr == "no-reply@huginn.local"
            assert to_addrs == ["ada@example.test"]
            calls.append(("send", message["To"]))
            return {"ada@example.test": (550, b"rejected")}

    def smtp_ssl_factory(*args, **kwargs):
        calls.append(("factory", (args, kwargs)))
        return FakeSmtp()

    monkeypatch.setattr(
        "huginn.management.delivery.smtp_lifecycle_mail_sender.smtplib.SMTP_SSL",
        smtp_ssl_factory,
    )
    monkeypatch.setattr(
        "huginn.management.delivery.smtp_lifecycle_mail_sender.ssl.create_default_context",
        lambda: "default-tls-context",
    )
    config = ManagementConfig(
        database_url="unused",
        web_origin="https://app.example.test",
        smtp_tls="implicit",
    )

    with pytest.raises(smtplib.SMTPRecipientsRefused):
        _send_smtp(
            config,
            LifecycleMailMessage("ada@example.test", "reset_password", "valid-proof"),
        )

    assert calls[0][0] == "factory"
    assert calls[0][1][1]["timeout"] == 30
    assert calls[0][1][1]["context"] == "default-tls-context"
    assert calls[1] == ("send", "ada@example.test")
