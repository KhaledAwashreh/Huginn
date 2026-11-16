"""Shared SMTP dialogue and cancellable process deadline."""

import smtplib
import ssl
from contextlib import suppress
from datetime import UTC, datetime
from email.message import EmailMessage
from multiprocessing import get_context
from time import monotonic

from huginn.management.application.constants.lifecycle_policy import (
    MAIL_TIMEOUT_SECONDS,
)
from huginn.management.application.errors.mail_pre_transport import (
    MailPreTransportError,
)
from huginn.management.config import ManagementConfig


def validate_credentials(config: ManagementConfig) -> None:
    if (config.smtp_username is None) != (config.smtp_password is None):
        raise ValueError("SMTP username and password must be configured together")


def send_smtp(
    config: ManagementConfig,
    email: EmailMessage,
    *,
    timeout_seconds: float | None = None,
) -> datetime:
    """SMTP dialogue; the public adapter supplies the cancellable total deadline."""
    timeout = MAIL_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    if config.smtp_tls == "implicit":
        client = smtplib.SMTP_SSL(
            config.smtp_host,
            config.smtp_port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
    else:
        client = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=timeout)
    accepted_at = None
    try:
        with client as connection:
            if config.smtp_tls == "starttls":
                connection.ehlo()
                connection.starttls(context=ssl.create_default_context())
                connection.ehlo()
            if config.smtp_username is not None:
                connection.login(config.smtp_username, config.smtp_password)
            refused = connection.send_message(
                email, from_addr=config.smtp_sender, to_addrs=[str(email["To"])]
            )
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
            accepted_at = datetime.now(UTC)
    except Exception:
        if accepted_at is None:
            raise
        # A failed QUIT cannot undo the already acknowledged SMTP handoff.
    return accepted_at


def _smtp_child(config, message, status, timeout_seconds):
    # IPC carries an acceptance timestamp or None; multiprocessing must not print a
    # secret-bearing exception or traceback from SMTP/rendering.
    try:
        accepted_at = send_smtp(config, message, timeout_seconds=timeout_seconds)
        result = accepted_at.isoformat()
    except BaseException:
        result = None
    try:
        status.send(result)
    except BaseException:
        pass
    finally:
        status.close()


def _stop_process(process, deadline):
    if process.is_alive():
        process.terminate()
        process.join(min(1.0, max(0.0, deadline - monotonic())))
    if process.is_alive():
        process.kill()
        process.join(max(0.0, deadline - monotonic()))
    if not process.is_alive():
        process.close()


def _close_quietly(resource):
    if resource is not None:
        with suppress(Exception):
            resource.close()


def send_email(
    config: ManagementConfig,
    email: EmailMessage,
    *,
    timeout_seconds: float = MAIL_TIMEOUT_SECONDS,
    error_message: str = "mail transport failed",
) -> datetime:
    """Bound SMTP plus process cleanup to one total attempt budget."""
    started = monotonic()
    deadline = started + timeout_seconds
    # Reserve two seconds for termination/kill/join inside the total budget.
    cleanup_budget = min(2.0, timeout_seconds / 10)
    network_budget = max(0.0, deadline - monotonic() - cleanup_budget)
    receiving = sending = None
    try:
        context = get_context("spawn")
        receiving, sending = context.Pipe(duplex=False)
        process = context.Process(
            target=_smtp_child,
            args=(config, email, sending, network_budget),
            daemon=True,
        )
    except Exception:
        _close_quietly(receiving)
        _close_quietly(sending)
        raise MailPreTransportError(error_message) from None
    launched = False
    try:
        process.start()
        launched = True
        sending.close()
        process.join(max(0.0, deadline - monotonic() - cleanup_budget))
        if process.is_alive() or process.exitcode != 0 or not receiving.poll():
            raise OSError(error_message)
        result = receiving.recv()
        if not isinstance(result, str):
            raise OSError(error_message)
        accepted_at = datetime.fromisoformat(result)
        if accepted_at.tzinfo is None or accepted_at.utcoffset() is None:
            raise OSError(error_message)
        return accepted_at.astimezone(UTC)
    except Exception:
        raise OSError(error_message) from None
    finally:
        if launched:
            # Cleanup must not expose private process/transport exceptions.
            with suppress(Exception):
                _stop_process(process, deadline)
        else:
            _close_quietly(process)
        _close_quietly(receiving)
        _close_quietly(sending)
