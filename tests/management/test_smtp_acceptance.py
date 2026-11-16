"""SMTP acceptance is distinct from later connection cleanup and observation."""

import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage

import pytest

from huginn.management.application.errors.mail_pre_transport import (
    MailPreTransportError,
)
from huginn.management.config import ManagementConfig
from huginn.management.delivery import smtp_transport


def test_known_acceptance_survives_quit_failure_and_retains_original_time(monkeypatch):
    accepted = datetime(2026, 11, 14, 12, tzinfo=UTC)
    cleanup = datetime(2026, 11, 14, 12, 1, tzinfo=UTC)
    current = [accepted]

    class Clock:
        @staticmethod
        def now(zone):
            assert zone == UTC
            return current[0]

    class Smtp:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            current[0] = cleanup
            raise smtplib.SMTPServerDisconnected("Connection ended after acceptance")

        def send_message(self, message, **_):
            return {}

    monkeypatch.setattr(smtp_transport, "datetime", Clock, raising=False)
    monkeypatch.setattr(smtp_transport.smtplib, "SMTP", lambda *_, **__: Smtp())
    message = EmailMessage()
    message["To"] = "recipient@example.test"
    assert smtp_transport.send_smtp(ManagementConfig("unused"), message) == accepted
    assert current[0] == cleanup


def _transport_context(payload, *, has_payload=True, eof=False):
    class Endpoint:
        def poll(self):
            return has_payload

        def recv(self):
            if eof:
                raise EOFError
            return payload

        def close(self):
            pass

    class Process:
        exitcode = 0

        def start(self):
            pass

        def join(self, _timeout):
            pass

        def is_alive(self):
            return False

        def close(self):
            pass

    class Context:
        def Pipe(self, **_):
            return Endpoint(), Endpoint()

        def Process(self, **_):
            return Process()

    return Context()


@pytest.mark.parametrize(
    ("payload", "has_payload", "eof"),
    [
        (None, True, False),
        (True, True, False),
        ("not a timestamp", True, False),
        ("2026-11-14T12:00:00", True, False),
        (None, True, True),
        (None, False, False),
    ],
)
def test_missing_or_invalid_child_acknowledgement_never_invents_acceptance(
    monkeypatch, payload, has_payload, eof
):
    context = _transport_context(payload, has_payload=has_payload, eof=eof)
    monkeypatch.setattr(smtp_transport, "get_context", lambda _: context)
    with pytest.raises(OSError, match="mail transport failed"):
        smtp_transport.send_email(ManagementConfig("unused"), EmailMessage())


def test_parent_retains_child_acceptance_instant_and_normalizes_timezone(monkeypatch):
    context = _transport_context("2026-11-14T14:00:00+02:00")
    monkeypatch.setattr(smtp_transport, "get_context", lambda _: context)
    assert smtp_transport.send_email(
        ManagementConfig("unused"), EmailMessage()
    ) == datetime(2026, 11, 14, 12, tzinfo=UTC)


def test_child_reports_only_original_acceptance_timestamp_or_unknown(monkeypatch):
    accepted = datetime(2026, 11, 14, 12, tzinfo=UTC)
    sent = []

    class Endpoint:
        def send(self, value):
            sent.append(value)

        def close(self):
            pass

    monkeypatch.setattr(smtp_transport, "send_smtp", lambda *_, **__: accepted)
    smtp_transport._smtp_child(
        ManagementConfig("unused"), EmailMessage(), Endpoint(), 30
    )
    assert sent == [accepted.isoformat()]

    def failed(*_, **__):
        raise OSError("private SMTP detail")

    monkeypatch.setattr(smtp_transport, "send_smtp", failed)
    smtp_transport._smtp_child(
        ManagementConfig("unused"), EmailMessage(), Endpoint(), 30
    )
    assert sent == [accepted.isoformat(), None]


@pytest.mark.parametrize("phase", ["context", "pipe", "process"])
def test_failures_before_process_start_are_proven_pre_transport_and_sanitized(
    monkeypatch, phase
):
    closed = []

    def private_failure():
        raise OSError("private recipient body and claim token")

    class Endpoint:
        def close(self):
            closed.append(True)

    class Context:
        def Pipe(self, **kwargs):
            if phase == "pipe":
                private_failure()
            return Endpoint(), Endpoint()

        def Process(self, **kwargs):
            private_failure()

    def context(_):
        if phase == "context":
            private_failure()
        return Context()

    monkeypatch.setattr(smtp_transport, "get_context", context)
    with pytest.raises(MailPreTransportError, match="mail transport failed") as error:
        smtp_transport.send_email(ManagementConfig("unused"), EmailMessage())
    assert "private" not in str(error.value)
    assert len(closed) == (2 if phase == "process" else 0)


def test_exception_after_invoking_process_start_remains_ambiguous(monkeypatch):
    class Process:
        def start(self):
            raise OSError("private detail after possibly launching a child")

        def close(self):
            pass

    context = _transport_context(None)
    monkeypatch.setattr(context, "Process", lambda **kwargs: Process())
    monkeypatch.setattr(smtp_transport, "get_context", lambda _: context)
    with pytest.raises(OSError, match="mail transport failed") as error:
        smtp_transport.send_email(ManagementConfig("unused"), EmailMessage())
    assert not isinstance(error.value, MailPreTransportError)
    assert "private" not in str(error.value)
