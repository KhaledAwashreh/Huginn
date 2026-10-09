"""Fixed trusted commands for matching worker and stopped-owner recovery."""

import sys


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "worker":
        from huginn.matchmaking_control.presentation.cli.worker import main as run
    elif command == "reconcile":
        from huginn.matchmaking_control.presentation.cli.reconcile import main as run
    elif command == "executor":
        from huginn.matchmaking_control.presentation.cli.executor import main as run
    else:
        raise SystemExit(
            "usage: python -m huginn.matchmaking_control {worker|reconcile|executor}"
        )
    run(sys.argv[2:])


if __name__ == "__main__":
    main()
