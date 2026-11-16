"""Fail-closed child for legacy supervised Match creation commands."""

import argparse
import json
import logging
import sys
from dataclasses import asdict
from uuid import UUID

from huginn.pipeline_control.infrastructure.process_supervisor import current_identity


def main(argv=None):
    parser = argparse.ArgumentParser(description="Retired Matchmaking executor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-id", type=UUID)
    group.add_argument("--batch-request")
    parser.add_argument("--worker-id", type=UUID)
    parser.add_argument("--result-path")
    args = parser.parse_args(argv)
    if args.run_id and (args.worker_id is None or args.result_path is not None):
        parser.error("managed identity is required")
    if args.batch_request and (args.result_path is None or args.worker_id is not None):
        parser.error("batch output is required")
    print(json.dumps(asdict(current_identity())), flush=True)
    if sys.stdin.readline() != "GO\n":
        raise SystemExit(2)
    logging.basicConfig(level=logging.INFO)
    logging.getLogger(__name__).error(
        "Matchmaking executor retired (matchmaking_retired)"
    )
    raise SystemExit(3)


if __name__ == "__main__":
    main()
