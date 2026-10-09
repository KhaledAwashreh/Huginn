"""Pipeline operator commands."""

import argparse

from huginn.pipeline_control.presentation.cli import reconcile, worker


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline control")
    parser.add_argument("command", choices=("worker", "reconcile"))
    args, remaining = parser.parse_known_args()
    if args.command == "worker":
        worker.main(remaining)
    else:
        reconcile.main(remaining)


if __name__ == "__main__":
    main()
