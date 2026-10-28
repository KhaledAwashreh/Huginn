from dataclasses import FrozenInstanceError, replace
from email import message_from_bytes, policy

import pytest

from huginn.management.application.read_models.weekly_digest_message import (
    WeeklyDigestMessage,
)
from huginn.management.config import ManagementConfig
from huginn.management.delivery.smtp_digest_mail_sender import SmtpDigestMailSender
from tests.management.test_lifecycle_smtp import _smtp_sink


def _message():
    return WeeklyDigestMessage(
        "ada@example.test",
        "Your weekly Huginn matches",
        "Private company evidence\nhttps://example.test/source",
        "<weekly-2026-44@example.test>",
    )


def test_digest_delivers_plain_text_with_stable_message_id_and_configured_sender():
    with _smtp_sink() as server:
        sender = SmtpDigestMailSender(
            ManagementConfig(
                database_url="unused",
                smtp_host=server.server_address[0],
                smtp_port=server.server_address[1],
                smtp_sender="digest@example.test",
            )
        )
        sender.send(_message())
        sender.send(_message())
        assert len(server.messages) == 2
        for payload in server.messages:
            message = message_from_bytes(payload, policy=policy.default)
            assert message["To"] == "ada@example.test"
            assert message["From"] == "digest@example.test"
            assert message["Message-ID"] == _message().message_id
            assert message["Subject"] == _message().subject
            assert message.get_content_type() == "text/plain"
            assert message.get_content().splitlines() == _message().body.splitlines()


@pytest.mark.parametrize("field", ["recipient", "subject", "message_id"])
def test_digest_rejects_header_injection_before_transport(field):
    sender = SmtpDigestMailSender(ManagementConfig(database_url="unused", smtp_port=1))
    with pytest.raises(ValueError):
        sender.send(
            replace(_message(), **{field: "value\r\nBcc: attacker@example.test"})
        )


def test_digest_requires_paired_credentials():
    with pytest.raises(ValueError, match="configured together"):
        SmtpDigestMailSender(
            ManagementConfig(database_url="unused", smtp_username="user")
        )


def test_digest_value_is_frozen_and_keeps_recipient_and_body_private():
    message = _message()
    assert message.recipient not in repr(message)
    assert message.body not in repr(message)
    with pytest.raises(FrozenInstanceError):
        message.body = "changed"


@pytest.mark.parametrize(
    "recipient",
    ["ada@example.test,attacker@example.test", "ada@example.test\x00", "ada"],
)
def test_digest_rejects_invalid_recipient_before_transport(recipient):
    sender = SmtpDigestMailSender(ManagementConfig(database_url="unused", smtp_port=1))
    with pytest.raises(ValueError):
        sender.send(replace(_message(), recipient=recipient))
