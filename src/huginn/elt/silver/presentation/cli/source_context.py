"""Explicit read-only audit and additive capture commands for source context."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from huginn.elt.silver.infrastructure.json_report_writer import (
    FilesystemJsonReportWriter,
)
from huginn.elt.silver.services.source_context import run_audit, run_capture

_SOURCES = ("hn", "eu_startups", "yc")


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
        prog="python -m huginn.elt.silver.presentation.cli.source_context",
        description="Audit or explicitly capture context from stored Bronze records.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("audit", "capture"):
        child = commands.add_parser(command)
        child.add_argument("--source", required=True, choices=_SOURCES)
        child.add_argument("--limit", type=_positive_int)
        child.add_argument(
            "--summary",
            type=Path,
            help="write the aggregate JSON report to this local path (stdout by default)",
        )
        if command == "audit":
            child.add_argument(
                "--details",
                type=Path,
                nargs="?",
                const=Path(".local-runtime/source-context/audit-details.json"),
                help="write full normalized records to this local JSON artifact",
            )
    return parser


def _default_repository() -> object:
    from dotenv import load_dotenv

    load_dotenv()
    database_url = os.environ.get("HUGINN_DATABASE_URL")
    if not database_url:
        raise RuntimeError("HUGINN_DATABASE_URL is required")
    from huginn.elt.silver.repositories.source_context_repository import (
        SourceContextRepository,
    )

    return SourceContextRepository(database_url)


def main(
    argv: Sequence[str] | None = None,
    *,
    repository_factory: Callable[[], object] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        repository = (repository_factory or _default_repository)()
        if args.command == "audit":
            report = run_audit(
                args.source,
                repository,  # type: ignore[arg-type]
                limit=args.limit,
                details_path=args.details,
                summary_path=args.summary,
                report_writer=FilesystemJsonReportWriter(),
            )
        else:
            report = run_capture(
                args.source,
                repository,  # type: ignore[arg-type]
                limit=args.limit,
                summary_path=args.summary,
                report_writer=FilesystemJsonReportWriter(),
            )
        if args.summary is None:
            sys.stdout.write(
                json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n"
            )
        if report["outcomes"]["failed"]:  # type: ignore[index]
            return 1
        persistence = report.get("persistence")
        if isinstance(persistence, dict) and persistence.get("status") != "complete":
            return 1
        return 0
    except Exception as error:
        sys.stderr.write(
            json.dumps(
                {
                    "error": "source context command failed",
                    "error_type": type(error).__name__,
                }
            )
            + "\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
