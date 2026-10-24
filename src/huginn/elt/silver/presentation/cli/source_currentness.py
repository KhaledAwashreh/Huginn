"""Explicit currentness audit and reconciliation commands."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from huginn.elt.silver.infrastructure.json_report_writer import (
    FilesystemJsonReportWriter,
)
from huginn.elt.silver.repositories.protocols.source_currentness_repository import (
    LifecycleRepository,
)
from huginn.elt.silver.services.source_currentness import run_audit, run_reconcile
from huginn.elt.silver.types.source_context import SourceName

_SOURCES = ("hn", "yc", "eu_startups")


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("limit must be a positive integer") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("limit must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m huginn.elt.silver.presentation.cli.source_currentness",
        description="Audit or reconcile lifecycle facts for stored source records.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("audit", "reconcile"):
        child = commands.add_parser(command)
        child.add_argument("--source", required=True, choices=_SOURCES)
        child.add_argument("--limit", type=_positive_int)
        child.add_argument(
            "--summary",
            type=Path,
            help="write the aggregate JSON report to this local path",
        )
    return parser


def _default_repository() -> LifecycleRepository:
    from dotenv import load_dotenv

    load_dotenv()
    database_url = os.environ.get("HUGINN_DATABASE_URL")
    if not database_url:
        raise RuntimeError("HUGINN_DATABASE_URL is required")
    from huginn.elt.silver.repositories.source_currentness_repository import (
        PostgresLifecycleRepository,
    )

    return PostgresLifecycleRepository(database_url)


def main(
    argv: Sequence[str] | None = None,
    *,
    repository_factory: Callable[[], LifecycleRepository] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        repository = (repository_factory or _default_repository)()
        source = cast(SourceName, args.source)
        if args.command == "audit":
            report = run_audit(
                source,
                repository,
                limit=args.limit,
                summary_path=args.summary,
                report_writer=FilesystemJsonReportWriter(),
            )
        else:
            report = run_reconcile(
                source,
                repository,
                limit=args.limit,
                summary_path=args.summary,
                report_writer=FilesystemJsonReportWriter(),
            )
        if args.summary is None:
            sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        if report.get("error_type") == "KeyboardInterrupt":
            return 130
        return 1 if report["status"] != "complete" else 0
    except Exception as error:
        sys.stderr.write(
            json.dumps(
                {
                    "error": "currentness command failed",
                    "error_type": type(error).__name__,
                }
            )
            + "\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
