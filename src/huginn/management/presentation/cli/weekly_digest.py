"""Operator opt-in and a single bounded weekly-digest run, docs/weekly-digest.md."""

import argparse
import json
import logging
from uuid import UUID

from huginn.management.config import load_config

logger = logging.getLogger(__name__)


def _limit(value):
    result = int(value)
    if not 1 <= result <= 250:
        raise argparse.ArgumentTypeError("Limit must be between 1 and 250")
    return result


def main(
    argv=None,
    *,
    config_factory=load_config,
    subscriptions_factory=None,
    digest_factory=None,
):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    subscribe = commands.add_parser(
        "subscribe", help="Explicitly opt in one pilot user"
    )
    subscribe.add_argument("--user-id", required=True, type=UUID)
    subscribe.add_argument("--strategy-id", required=True, type=UUID)
    unsubscribe = commands.add_parser("unsubscribe")
    unsubscribe.add_argument("--user-id", required=True, type=UUID)
    send = commands.add_parser("send", help="Run once; schedule weekly with cron")
    send.add_argument("--limit", type=_limit, default=100)
    send.add_argument("--daily-limit", type=_limit, default=100)
    send.add_argument(
        "--dry-run",
        action="store_true",
        help="Count eligible subscriptions; no generation, reservations or SMTP",
    )
    args = parser.parse_args(argv)
    try:
        config = config_factory()
        if args.command == "send":
            result = digest_factory(config).run(
                limit=args.limit, daily_limit=args.daily_limit, dry_run=args.dry_run
            )
        else:
            service = subscriptions_factory(config)
            if args.command == "subscribe":
                service.subscribe(args.user_id, args.strategy_id)
            else:
                service.unsubscribe(args.user_id)
            result = {
                "state": args.command + "d"
                if args.command == "subscribe"
                else "unsubscribed"
            }
        print(json.dumps(result))
        return 1 if result.get("failed", 0) or result.get("unknown", 0) else 0
    except Exception as error:
        logger.error("Weekly digest command failed (%s)", type(error).__name__)
        print(json.dumps({"error": "weekly_digest_unavailable"}))
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
