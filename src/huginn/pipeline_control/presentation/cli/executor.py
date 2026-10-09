"""Trusted child. No ELT stage starts before durable parent acknowledgement."""

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from uuid import UUID

from huginn.config import load_config
from huginn.pipeline_control.application.errors.execution import TrackingUncertainError
from huginn.pipeline_control.infrastructure.elt_pipeline_executor import (
    EltPipelineExecutor,
)
from huginn.pipeline_control.infrastructure.process_supervisor import current_identity


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--invocation-id", required=True)
    args = parser.parse_args()
    invocation_id = (
        None if args.invocation_id == "standalone" else UUID(args.invocation_id)
    )
    print(json.dumps(asdict(current_identity())), flush=True)
    if sys.stdin.readline() != "GO\n":
        raise SystemExit(2)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    logging.basicConfig(level=logging.INFO)
    try:
        outcome = EltPipelineExecutor(load_config()).run(invocation_id)
    except TrackingUncertainError:
        logging.getLogger(__name__).exception("Managed tracking interrupted")
        outcome = 3
    except Exception:
        logging.getLogger(__name__).exception("Pipeline executor failed")
        outcome = 1
    raise SystemExit(outcome)


if __name__ == "__main__":
    main()
