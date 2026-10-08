"""Offline OpenAPI export, web-ui-foundation shared tooling contract."""

import argparse
import json
from pathlib import Path

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export OpenAPI without connecting to runtime services."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    app = create_app(
        ManagementConfig(
            "postgresql://unused:unused@127.0.0.1:1/openapi_export",
            environment="test",
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(app.openapi(), sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
