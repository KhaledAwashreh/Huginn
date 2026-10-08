"""Plain-text email for resetting an account password."""

import re
from email.message import EmailMessage
from email.utils import parseaddr
from urllib.parse import quote, urlsplit

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")
_PROOF_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,1024}$")


def render_reset_mail(
    *, recipient: str, sender: str, token: str, web_origin: str
) -> EmailMessage:
    """Build a password reset message with proof data in the URL fragment."""
    _validate_inputs(recipient, sender, token, web_origin)
    link = f"{web_origin.rstrip('/')}/reset-password#token={quote(token, safe='')}"
    message = EmailMessage()
    message["To"] = recipient
    message["From"] = sender
    message["Subject"] = "Reset your Huginn password"
    message.set_content(
        "Use this link to choose a new password for your Huginn account:\n\n"
        f"{link}\n\n"
        "If you did not request this, you can ignore this message."
    )
    return message


def _validate_inputs(recipient: str, sender: str, token: str, web_origin: str) -> None:
    if not _valid_email(recipient):
        raise ValueError("invalid lifecycle mail recipient")
    if not _valid_email(sender):
        raise ValueError("invalid lifecycle mail sender")
    if not isinstance(token, str) or _PROOF_PATTERN.fullmatch(token) is None:
        raise ValueError("invalid lifecycle mail proof")
    _validate_web_origin(web_origin)


def _valid_email(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 254
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
        and _EMAIL_PATTERN.fullmatch(value) is not None
        and parseaddr(value, strict=True) == ("", value)
    )


def _validate_web_origin(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise ValueError("invalid trusted web origin")
    try:
        origin = urlsplit(value)
        port = origin.port
    except ValueError as exc:
        raise ValueError("invalid trusted web origin") from exc
    if (
        origin.scheme not in {"http", "https"}
        or not origin.hostname
        or origin.username is not None
        or origin.password is not None
        or origin.path not in {"", "/"}
        or origin.query
        or origin.fragment
        or port == 0
    ):
        raise ValueError("invalid trusted web origin")
