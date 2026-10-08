"""Bounded SMTP adapter for account lifecycle messages."""

import smtplib
import ssl
from email.message import EmailMessage
from multiprocessing import get_context
from time import monotonic

from huginn.management.application.constants.lifecycle_policy import (
    MAIL_TIMEOUT_SECONDS,
)
from huginn.management.application.protocols.lifecycle_mail_sender import (
    LifecycleMailSender,
)
from huginn.management.application.read_models.lifecycle_mail_message import (
    LifecycleMailMessage,
)
from huginn.management.config import ManagementConfig
from huginn.management.delivery.templates.reset_password import render_reset_mail
from huginn.management.delivery.templates.verify_email import (
    render_verification_mail,
)


def _render(config: ManagementConfig, message: LifecycleMailMessage) -> EmailMessage:
    if not config.web_origin:
        raise ValueError("trusted web origin is required for lifecycle mail")
    if message.purpose == "verify_email":
        renderer = render_verification_mail
    elif message.purpose == "reset_password":
        renderer = render_reset_mail
    else:
        raise ValueError("invalid lifecycle mail purpose")
    return renderer(
        recipient=message.recipient,
        sender=config.smtp_sender,
        token=message.token,
        web_origin=config.web_origin,
    )


def _send_smtp(
    config: ManagementConfig,
    message: LifecycleMailMessage,
    *,
    timeout_seconds: float | None = None,
) -> None:
    """SMTP dialogue; the public adapter supplies the cancellable total deadline."""
    email = _render(config, message)
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
            email, from_addr=config.smtp_sender, to_addrs=[message.recipient]
        )
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)


def _smtp_child(config, message, status, timeout_seconds):
    # Child failures carry only a Boolean; multiprocessing must not print a
    # secret-bearing exception or traceback from SMTP/rendering.
    try:
        _send_smtp(config, message, timeout_seconds=timeout_seconds)
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


class SmtpLifecycleMailSender(LifecycleMailSender):
    """Bound SMTP plus sender-process cleanup to one total 30-second budget."""

    def __init__(self, config: ManagementConfig) -> None:
        if not config.web_origin:
            raise ValueError("trusted web origin is required for lifecycle mail")
        if (config.smtp_username is None) != (config.smtp_password is None):
            raise ValueError("SMTP username and password must be configured together")
        self._config = config

    def send(self, message: LifecycleMailMessage) -> None:
        started = monotonic()
        _render(self._config, message)
        deadline = started + MAIL_TIMEOUT_SECONDS
        # Reserve two seconds for termination/kill/join inside the total budget.
        cleanup_budget = min(2.0, MAIL_TIMEOUT_SECONDS / 10)
        network_budget = max(0.0, deadline - monotonic() - cleanup_budget)
        context = get_context("spawn")
        receiving, sending = context.Pipe(duplex=False)
        process = context.Process(
            target=_smtp_child,
            args=(self._config, message, sending, network_budget),
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
                raise OSError("lifecycle mail transport failed")
        except Exception:
            raise OSError("lifecycle mail transport failed") from None
        finally:
            if launched:
                _stop_process(process, deadline)
            else:
                process.close()
            receiving.close()
            sending.close()
