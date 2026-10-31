"""Exercise the remote deployment entry point without touching Docker or EC2."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/deploy-ec2.py"
COMMIT = "a" * 40
PREVIOUS = "b" * 40
IMAGE = "ghcr.io/example/huginn@sha256:" + "c" * 64


@pytest.fixture
def deployment(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    original = (
        b"# keep operator settings\nPOSTGRES_PASSWORD=private-secret\n"
        b"HUGINN_IMAGE=old-image\nHUGINN_HOST_PORT=80\n"
        b"HUGINN_BIND_ADDRESS=0.0.0.0\n"
    )
    (checkout / ".env").write_bytes(original)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "fake"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "name = pathlib.Path(sys.argv[0]).name\n"
        "args = sys.argv[1:]\n"
        "if name == 'sudo':\n"
        "    name, args = args[1], args[2:]\n"
        "with open(os.environ['COMMAND_LOG'], 'a') as log:\n"
        "    log.write(json.dumps([name, *args]) + '\\n')\n"
        "if os.environ.get('FAIL_COMMAND') == ' '.join([name, *args]):\n"
        "    sys.exit(17)\n"
        "if os.environ.get('FAIL_READINESS') and name == 'docker' and args[:2] == ['compose', 'exec']:\n"
        "    sys.exit(19)\n"
        "if name == 'git':\n"
        "    if args[:1] == ['status']:\n"
        "        print(os.environ.get('DIRTY', ''), end='')\n"
        "    elif args == ['rev-parse', 'HEAD']:\n"
        f"        print('{PREVIOUS}')\n"
        "    elif args == ['rev-parse', 'origin/master']:\n"
        f"        print(os.environ.get('LATEST', '{COMMIT}'))\n"
        "    elif args[:1] == ['diff']:\n"
        "        print(os.environ.get('SCHEMA_CHANGE', ''), end='')\n"
        "elif name == 'docker' and args[:2] == ['image', 'inspect']:\n"
        f"    print(os.environ.get('IMAGE_COMMIT', '{COMMIT}'))\n"
    )
    fake.chmod(0o755)
    for name in ("git", "sudo"):
        (binaries / name).symlink_to(fake)
    log = tmp_path / "commands.jsonl"
    environment = {**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}"}
    environment["COMMAND_LOG"] = str(log)

    def run(**changes):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(checkout), COMMIT, IMAGE],
            capture_output=True,
            text=True,
            env={**environment, **changes},
            timeout=10,
        )

    def commands():
        return [json.loads(line) for line in log.read_text().splitlines()]

    return checkout, original, run, commands


def test_deploy_pulls_exact_image_preserves_settings_and_checks_readiness(deployment):
    checkout, original, run, commands = deployment
    result = run()
    assert result.returncode == 0, result.stderr
    assert (checkout / ".env").read_bytes() == original.replace(
        b"HUGINN_IMAGE=old-image", f"HUGINN_IMAGE={IMAGE}".encode()
    )
    assert (checkout / ".env").stat().st_mode & 0o777 == 0o600
    calls = commands()
    assert ["docker", "pull", IMAGE] in calls
    assert ["git", "checkout", "--detach", COMMIT] in calls
    assert ["docker", "compose", "pull"] in calls
    assert [
        "docker",
        "compose",
        "up",
        "-d",
        "--no-build",
        "--wait",
        "--wait-timeout",
        "180",
    ] in calls
    assert any(
        call[:6] == ["docker", "compose", "exec", "-T", "app", "python"]
        for call in calls
    )
    assert "private-secret" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"DIRTY": " M compose.yaml\n"}, "tracked changes"),
        ({"SCHEMA_CHANGE": "db/schema/new-table.sql\n"}, "schema"),
        ({"IMAGE_COMMIT": PREVIOUS}, "revision"),
    ],
)
def test_preflight_failure_leaves_config_and_containers_untouched(
    deployment, changes, message
):
    checkout, original, run, commands = deployment
    result = run(**changes)
    assert result.returncode != 0
    assert message in result.stderr
    assert (checkout / ".env").read_bytes() == original
    assert not any(call[:3] == ["docker", "compose", "up"] for call in commands())


def test_stale_workflow_does_not_replace_a_newer_release(deployment):
    checkout, original, run, commands = deployment
    result = run(LATEST="d" * 40)
    assert result.returncode == 0, result.stderr
    assert "Skipping" in result.stdout
    assert (checkout / ".env").read_bytes() == original
    assert not any(call[0] == "docker" for call in commands())


def test_missing_private_configuration_stops_before_deployment(deployment):
    checkout, _, run, _ = deployment
    (checkout / ".env").unlink()
    result = run()
    assert result.returncode != 0
    assert ".env" in result.stderr
    assert not (checkout / ".env").exists()


@pytest.mark.parametrize(
    "command",
    [
        f"docker pull {IMAGE}",
        "docker compose pull",
        "docker compose up -d --no-build --wait --wait-timeout 180",
    ],
)
def test_deployment_failure_is_reported_and_restores_previous_configuration(
    deployment, command
):
    checkout, original, run, _ = deployment
    result = run(FAIL_COMMAND=command)
    assert result.returncode != 0
    assert (checkout / ".env").read_bytes() == original
    assert "failed" in result.stderr.lower()


def test_missing_image_setting_is_added_without_changing_other_settings(deployment):
    checkout, original, run, _ = deployment
    original = original.replace(b"HUGINN_IMAGE=old-image\n", b"")
    (checkout / ".env").write_bytes(original)
    result = run()
    assert result.returncode == 0, result.stderr
    assert (
        checkout / ".env"
    ).read_bytes() == original + f"HUGINN_IMAGE={IMAGE}\n".encode()


def test_failed_readiness_restores_config_and_warns_containers_may_have_changed(
    deployment,
):
    checkout, original, run, commands = deployment
    result = run(FAIL_READINESS="1")
    assert result.returncode != 0
    assert (checkout / ".env").read_bytes() == original
    assert "Containers may have changed" in result.stderr
    assert ["git", "checkout", "--detach", PREVIOUS] in commands()
