import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/configure-compose.py"


def test_compose_configuration_generates_private_persistent_secrets(tmp_path):
    target = tmp_path / ".env.compose"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    values = dict(
        line.split("=", 1)
        for line in target.read_text().splitlines()
        if line and not line.startswith("#")
    )
    assert len(base64.urlsafe_b64decode(values["HUGINN_LIFECYCLE_PROOF_KEY"])) == 32
    assert len(bytes.fromhex(values["POSTGRES_PASSWORD"])) >= 24
    assert os.stat(target).st_mode & 0o777 == 0o600
    assert values["POSTGRES_PASSWORD"] not in result.stdout + result.stderr
    assert values["HUGINN_LIFECYCLE_PROOF_KEY"] not in result.stdout + result.stderr
    assert values["HUGINN_BOOTSTRAP_ADMIN_USERNAME"] == "Khaled"
    assert 8 <= len(values["HUGINN_BOOTSTRAP_ADMIN_PASSWORD"]) <= 16
    assert (
        values["HUGINN_BOOTSTRAP_ADMIN_PASSWORD"] not in result.stdout + result.stderr
    )
    assert values["HUGINN_BOOTSTRAP_SECOND_ADMIN_USERNAME"] == "Craig"
    second = values["HUGINN_BOOTSTRAP_SECOND_ADMIN_PASSWORD"]
    assert 8 <= len(second) <= 16
    assert second != values["HUGINN_BOOTSTRAP_ADMIN_PASSWORD"]
    assert second not in result.stdout + result.stderr
    original = target.read_bytes()
    again = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target)], capture_output=True
    )
    assert again.returncode != 0
    assert target.read_bytes() == original


def test_adding_admin_to_older_config_preserves_existing_secrets(tmp_path):
    target = tmp_path / ".env.compose"
    original = (
        "POSTGRES_PASSWORD=keep-db-password\nHUGINN_LIFECYCLE_PROOF_KEY=keep-key\n"
    )
    target.write_text(original)
    command = [sys.executable, str(SCRIPT), "--output", str(target), "--add-admin"]
    assert subprocess.run(command, capture_output=True).returncode == 0
    updated = target.read_text()
    assert updated.startswith(original)
    assert "HUGINN_BOOTSTRAP_ADMIN_USERNAME=Khaled" in updated
    assert subprocess.run(command, capture_output=True).returncode == 0
    assert target.read_text() == updated
    assert os.stat(target).st_mode & 0o777 == 0o600


def test_partial_admin_configuration_is_never_silently_replaced(tmp_path):
    target = tmp_path / ".env.compose"
    original = "HUGINN_BOOTSTRAP_ADMIN_PASSWORD=existing-password\n"
    target.write_text(original)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target), "--add-admin"],
        capture_output=True,
    )
    assert result.returncode != 0
    assert target.read_text() == original


def test_adding_second_admin_preserves_complete_existing_primary(tmp_path):
    target = tmp_path / ".env"
    original = (
        "POSTGRES_PASSWORD=keep-db\nHUGINN_LIFECYCLE_PROOF_KEY=keep-key\n"
        "HUGINN_BOOTSTRAP_ADMIN_USERNAME=existing-admin\n"
        "HUGINN_BOOTSTRAP_ADMIN_EMAIL=existing@example.test\n"
        "HUGINN_BOOTSTRAP_ADMIN_PASSWORD=KeepPassword!123\n"
    )
    target.write_text(original)
    command = [sys.executable, str(SCRIPT), "--output", str(target), "--add-admin"]
    assert subprocess.run(command, capture_output=True).returncode == 0
    updated = target.read_text()
    assert updated.startswith(original)
    assert "HUGINN_BOOTSTRAP_SECOND_ADMIN_USERNAME=Craig" in updated
    assert subprocess.run(command, capture_output=True).returncode == 0
    assert target.read_text() == updated


def test_partial_second_admin_never_changes_existing_file(tmp_path):
    target = tmp_path / ".env"
    original = "HUGINN_BOOTSTRAP_SECOND_ADMIN_PASSWORD=existing-password\n"
    target.write_text(original)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target), "--add-admin"],
        capture_output=True,
    )
    assert result.returncode != 0
    assert target.read_text() == original


def test_complete_but_empty_admin_setting_is_rejected_without_changes(tmp_path):
    target = tmp_path / ".env"
    original = (
        "HUGINN_BOOTSTRAP_ADMIN_USERNAME=Khaled\n"
        "HUGINN_BOOTSTRAP_ADMIN_EMAIL=khaled@example.test\n"
        "HUGINN_BOOTSTRAP_ADMIN_PASSWORD=\n"
    )
    target.write_text(original)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target), "--add-admin"],
        capture_output=True,
    )
    assert result.returncode != 0
    assert target.read_text() == original


@pytest.mark.parametrize(
    "image",
    (
        None,
        "ghcr.io/example/huginn:" + "a" * 40,
        "ghcr.io/example/huginn@sha256:" + "b" * 64,
    ),
)
def test_compose_resolves_shared_image_without_changing_infrastructure(tmp_path, image):
    if shutil.which("docker") is None:
        pytest.skip(
            "Docker Compose is required to resolve the deployment configuration"
        )
    target = tmp_path / ".env"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target)],
        check=True,
        capture_output=True,
    )
    # Exercise the fallback independently of the generated template default.
    target.write_text(
        "\n".join(
            line
            for line in target.read_text().splitlines()
            if not line.startswith("HUGINN_IMAGE=")
        )
        + "\n"
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("HUGINN_") and key != "POSTGRES_PASSWORD"
    }
    if image is not None:
        environment["HUGINN_IMAGE"] = image
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(target),
            "--profile",
            "jobs",
            "config",
            "--format",
            "json",
        ],
        cwd=SCRIPT.parents[1],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    for name in (
        "app",
        "admin-seed",
        "collection-worker",
        "matching-worker",
        "mail-worker",
        "weekly-digest",
    ):
        assert services[name]["image"] == (image or "huginn-app:local"), name
    assert services["db"]["image"] == "postgres:16-alpine"
    assert services["mailpit"]["image"] == "axllent/mailpit:v1.27.10"
