"""Explicit read-only attribute assessment; never runs a promotion."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from uuid import UUID

from huginn.elt.gold.attribute_promotion.runner import json_default, run_assessment
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow


def _repository():
    from dotenv import load_dotenv

    from huginn.elt.gold.attribute_promotion.repository import (
        PostgresAssessmentRepository,
    )

    load_dotenv()
    url = os.environ.get("HUGINN_DATABASE_URL")
    if not url:
        raise RuntimeError("HUGINN_DATABASE_URL is required")
    return PostgresAssessmentRepository(url)


def _write_private(path: Path, value: object):
    """Atomic output with mode 0600 even if an existing file was public."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".assessment-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, default=json_default, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(temporary)
        raise


def _criteria(path: Path | None) -> dict[str, CompiledCriteria]:
    if path is None:
        # Mechanical synthetic case, never a user's private ICP.
        return {
            "synthetic_b2b_small_usa": CompiledCriteria(
                ("B2B",), ("0-10",), ("USA",), (), (), ()
            )
        }
    document = json.loads(path.read_text())
    if not isinstance(document, dict) or not document:
        raise ValueError("criteria must be a nonempty named object")
    result = {}
    names = (
        "industries",
        "company_sizes",
        "countries",
        "excluded_company_ids",
        "excluded_industries",
        "excluded_countries",
    )
    for name, values in document.items():
        if (
            not isinstance(name, str)
            or not isinstance(values, dict)
            or set(values) - set(names)
        ):
            raise ValueError("invalid synthetic criteria object")
        arguments = {}
        for field in names:
            value = values.get(field, [])
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                raise ValueError("criterion fields must be arrays of nonblank strings")
            arguments[field] = (
                tuple(UUID(item) for item in value)
                if field == "excluded_company_ids"
                else tuple(value)
            )
        if any(not arguments[field] for field in names[:3]):
            raise ValueError("industries, company_sizes and countries are required")
        if set(arguments["company_sizes"]) - {"0-10", "11-100", "101-1000", "1001+"}:
            raise ValueError("invalid company size band")
        result[name] = CompiledCriteria(**arguments)
    return result


def main(
    argv: Sequence[str] | None = None, *, repository_factory: Callable | None = None
) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only guarded attribute assessment and synthetic matcher impact."
    )
    parser.add_argument(
        "--cutoff", required=True, help="Inclusive timezone-aware ISO timestamp"
    )
    parser.add_argument(
        "--as-of", required=True, help="Inclusive timezone-aware ISO timestamp"
    )
    parser.add_argument(
        "--criteria", type=Path, help="Named synthetic compiled criteria JSON"
    )
    parser.add_argument(
        "--limit", type=int, help="Limit companies deterministically; sample only"
    )
    parser.add_argument("--summary", type=Path)
    parser.add_argument(
        "--receipts", type=Path, help="Restricted local field lineage (0600)"
    )
    args = parser.parse_args(argv)
    try:
        window = SignalWindow(
            datetime.fromisoformat(args.cutoff), datetime.fromisoformat(args.as_of)
        )
        if (
            args.summary
            and args.receipts
            and args.summary.resolve() == args.receipts.resolve()
        ):
            raise ValueError("summary and receipts must be different paths")
        criteria = _criteria(args.criteria)
        result = run_assessment(
            (repository_factory or _repository)(),
            criteria,
            {"requested": window},
            limit=args.limit,
        )
        if args.receipts:
            _write_private(args.receipts, result.receipts)
        if args.summary:
            _write_private(args.summary, result.summary)
        else:
            sys.stdout.write(
                json.dumps(result.summary, default=json_default, indent=2) + "\n"
            )
        return 0
    except Exception as error:
        sys.stderr.write(
            json.dumps(
                {
                    "error": "attribute assessment failed",
                    "error_type": type(error).__name__,
                }
            )
            + "\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
