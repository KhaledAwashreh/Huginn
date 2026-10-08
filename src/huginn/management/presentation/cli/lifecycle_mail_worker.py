"""Dedicated lifecycle mail worker process."""

import argparse
import logging
import signal
from collections.abc import Callable, Sequence
from threading import Event

from huginn.management.application.requests.deliver_lifecycle_mail_request import (
    DeliverLifecycleMailRequest,
)
from huginn.management.application.services.deliver_lifecycle_mail_service import (
    DeliverLifecycleMailService,
)
from huginn.management.config import ManagementConfig, load_config
from huginn.management.delivery.smtp_lifecycle_mail_sender import (
    SmtpLifecycleMailSender,
)
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.management.persistence.database.unit_of_work import UnitOfWork
from huginn.management.persistence.repositories.account import PostgresAccountRepository
from huginn.management.persistence.repositories.account_lifecycle_proof import (
    PostgresAccountLifecycleProofRepository,
)
from huginn.management.persistence.repositories.account_recovery_identity import (
    PostgresAccountRecoveryIdentityRepository,
)
from huginn.management.persistence.repositories.lifecycle_mail_outbox import (
    PostgresLifecycleMailOutboxRepository,
)
from huginn.management.security.encrypted_proof_cipher import EncryptedProofCipher

logger = logging.getLogger(__name__)


def _build_service(
    config: ManagementConfig | None = None,
) -> DeliverLifecycleMailService:
    config = config if config is not None else load_config()
    if not config.lifecycle_proof_key or not config.web_origin:
        raise RuntimeError(
            "lifecycle encryption key and trusted web origin are required"
        )
    factory = ManagementConnectionFactory(config.database_url)
    return DeliverLifecycleMailService(
        lambda: UnitOfWork(factory),
        outbox_factory=lambda uow: PostgresLifecycleMailOutboxRepository(
            uow.connection
        ),
        accounts_factory=lambda uow: PostgresAccountRepository(uow.connection),
        recovery_identities_factory=lambda uow: (
            PostgresAccountRecoveryIdentityRepository(uow.connection)
        ),
        proofs_factory=lambda uow: PostgresAccountLifecycleProofRepository(
            uow.connection
        ),
        cipher=EncryptedProofCipher(config.lifecycle_proof_key),
        sender=SmtpLifecycleMailSender(config),
    )


def _poll_seconds(value: str) -> int:
    try:
        seconds = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "poll seconds must be between 1 and 60"
        ) from exc
    if not 1 <= seconds <= 60:
        raise argparse.ArgumentTypeError("poll seconds must be between 1 and 60")
    return seconds


def main(
    argv: Sequence[str] | None = None,
    *,
    service_factory: Callable[[], DeliverLifecycleMailService] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Dispatch durable account lifecycle mail"
    )
    parser.add_argument(
        "--once", action="store_true", help="claim at most one message and exit"
    )
    parser.add_argument("--poll-seconds", type=_poll_seconds, default=5)
    args = parser.parse_args(argv)
    stopping = Event()
    previous = {}

    def stop(signum, frame):
        stopping.set()

    try:
        service = (service_factory or _build_service)()
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, stop)
        while not stopping.is_set():
            result = service.execute(DeliverLifecycleMailRequest())
            if args.once:
                break
            if result.outcome == "idle":
                stopping.wait(args.poll_seconds)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        logger.error("Lifecycle mail worker failed (%s)", type(exc).__name__)
        return 1
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
