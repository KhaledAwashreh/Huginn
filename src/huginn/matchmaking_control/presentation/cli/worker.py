"""Retired queue-worker entry point for legacy Match creation runs."""

import argparse
import logging

from huginn.matchmaking.application.errors.retired import MatchmakingRetiredError

logger = logging.getLogger(__name__)


def run_once(uow_factory=None, guard_factory=None, supervisor_factory=None):
    """The retired worker never claims or changes durable run records."""
    del uow_factory, guard_factory, supervisor_factory
    raise MatchmakingRetiredError


def main(argv=None):
    parser = argparse.ArgumentParser(description="Retired legacy Match creation worker")
    parser.add_argument("--once", action="store_true")
    parser.parse_args(argv)
    logger.error("Matchmaking worker retired (matchmaking_retired)")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
