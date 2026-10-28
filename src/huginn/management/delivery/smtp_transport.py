"""Shared SMTP dialogue and cancellable process deadline."""

import smtplib
import ssl
from email.message import EmailMessage
from multiprocessing import get_context
from time import monotonic

from huginn.management.application.constants.lifecycle_policy import (
    MAIL_TIMEOUT_SECONDS,
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
) -> None:
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


def _smtp_child(config, message, status, timeout_seconds):
    # Child failures carry only a Boolean; multiprocessing must not print a
    # secret-bearing exception or traceback from SMTP/rendering.
    try:
        send_smtp(config, message, timeout_seconds=timeout_seconds)
        succeeded = True
    except BaseException:
        succeeded = False
    try:
        status.send(succeeded)
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


def send_email(
    config: ManagementConfig,
    email: EmailMessage,
    *,
    timeout_seconds: float = MAIL_TIMEOUT_SECONDS,
    error_message: str = "mail transport failed",
) -> None:
    """Bound SMTP plus process cleanup to one total attempt budget."""
    started = monotonic()
    deadline = started + timeout_seconds
    # Reserve two seconds for termination/kill/join inside the total budget.
    cleanup_budget = min(2.0, timeout_seconds / 10)
    network_budget = max(0.0, deadline - monotonic() - cleanup_budget)
    context = get_context("spawn")
    receiving, sending = context.Pipe(duplex=False)
    process = context.Process(
        target=_smtp_child,
        args=(config, email, sending, network_budget),
        daemon=True,
    )
    launched = False
    try:
        process.start()
        launched = True
        sending.close()
        process.join(max(0.0, deadline - monotonic() - cleanup_budget))
        if (
            process.is_alive()
            or process.exitcode != 0
            or not receiving.poll()
            or receiving.recv() is not True
        ):
            raise OSError(error_message)
    except Exception:
        raise OSError(error_message) from None
    finally:
        if launched:
            _stop_process(process, deadline)
        else:
            process.close()
        receiving.close()
        sending.close()
