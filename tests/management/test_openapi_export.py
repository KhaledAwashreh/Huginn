"""Offline schema export, web-ui-foundation shared tooling contract."""

import json
import os
import subprocess
import sys
from pathlib import Path


def test_schema_export_is_offline_deterministic_and_ignores_runtime_configuration(
    tmp_path,
):
    root = Path(__file__).resolve().parents[2]
    output = tmp_path / "openapi.json"
    environment = {
        **os.environ,
        "HUGINN_MANAGEMENT_ENVIRONMENT": "not-valid",
    }
    command = [
        sys.executable,
        str(root / "scripts/export-management-openapi.py"),
        "--output",
        str(output),
    ]
    first = subprocess.run(
        command, cwd=root, env=environment, capture_output=True, text=True, timeout=20
    )
    assert first.returncode == 0, first.stderr
    original = output.read_bytes()
    second = subprocess.run(
        command, cwd=root, env=environment, capture_output=True, text=True, timeout=20
    )
    assert second.returncode == 0, second.stderr
    assert output.read_bytes() == original
    schema = json.loads(original)
    assert "get" in schema["paths"]["/api/v1/sessions/current"]
    assert "delete" in schema["paths"]["/api/v1/sessions/current"]
