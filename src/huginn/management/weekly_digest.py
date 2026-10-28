"""Launch the scheduled digest command using its concrete composition root."""

import logging

from huginn.management.presentation.cli import weekly_digest
from huginn.management.weekly_digest_bootstrap import (
    create_digest_subscription_service,
    create_weekly_digest_service,
)


def main(argv=None):
    return weekly_digest.main(
        argv,
        subscriptions_factory=create_digest_subscription_service,
        digest_factory=create_weekly_digest_service,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
