"""Explicit JSON research ranking operator; never connects to a database."""

import argparse
import json
import sys
from pathlib import Path

from huginn.matchmaking.application.serializers.research_ranking import (
    serialize_research_ranking,
)
from huginn.matchmaking.application.services.research_ranking_service import (
    ResearchRankingService,
)
from huginn.matchmaking.presentation.parsers.ranking_input import parse_ranking_input

MAX_INPUT_BYTES = 16 * 1024 * 1024


class _RankingArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("Invalid ranking command-line arguments")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Nonfinite JSON numbers are unsupported")


def _error(code, message):
    json.dump({"error": {"code": code, "message": message}}, sys.stdout)
    sys.stdout.write("\n")


def main(argv=None):
    parser = _RankingArgumentParser(
        prog="python -m huginn.matchmaking.presentation.ranking_cli",
        description=__doc__,
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="New output file; existing snapshots are never overwritten",
    )
    parser.add_argument("--reranker", choices=("none", "fastembed"), default="none")
    parser.add_argument("--model-cache", type=str)
    try:
        args = parser.parse_args(argv)
        if args.output is not None and args.output.exists():
            raise FileExistsError("Ranking output already exists")
        with args.input.open("rb") as stream:
            source = stream.read(MAX_INPUT_BYTES + 1)
        if len(source) > MAX_INPUT_BYTES:
            raise ValueError("Ranking input exceeds work bounds")
        payload = json.loads(
            source, object_pairs_hook=_pairs, parse_constant=_reject_constant
        )
        request = parse_ranking_input(payload)
        # Validate all evidence/as-of constraints before any optional model download.
        from huginn.matchmaking.domain.policies.research_scoring import score_assessment

        for assessment in request.assessments:
            score_assessment(assessment, request.as_of)
        reranker = None
        if args.reranker == "fastembed":
            if request.semantic_query is None:
                raise ValueError("Explicit semantic query required")
            from huginn.matchmaking.infrastructure.fastembed_semantic_reranker import (
                FastEmbedSemanticReranker,
            )

            reranker = FastEmbedSemanticReranker(cache_dir=args.model_cache)
        result = serialize_research_ranking(
            ResearchRankingService(reranker).execute(request)
        )
        text = (
            json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False)
            + "\n"
        )
        if args.output is None:
            sys.stdout.write(text)
        else:
            from huginn.matchmaking.presentation.write_ranking_output import (
                write_ranking_output,
            )

            write_ranking_output(args.output, text)
        return 0
    except ValueError, TypeError, UnicodeError, RecursionError:
        _error("invalid_ranking_input", "Invalid source-linked ranking input")
        return 2
    except OSError:
        _error(
            "ranking_file_unavailable", "Ranking input or output file is unavailable"
        )
        return 2
    except Exception:
        _error(
            "ranking_unavailable",
            "Ranking or the configured semantic model is unavailable",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
