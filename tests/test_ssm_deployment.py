"""Exercise the SSM dispatcher through a fake AWS CLI, without AWS access."""

import ast
import base64
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/dispatch-ec2-deployment.py"
REMOTE_SCRIPT = SCRIPT.with_name("deploy-ec2.py")
COMMIT = "a" * 40
IMAGE = "ghcr.io/example/huginn@sha256:" + "c" * 64


@pytest.fixture
def dispatcher(tmp_path):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    aws = binaries / "aws"
    aws.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['COMMAND_LOG'], 'a') as log:\n"
        "    log.write(json.dumps(args) + '\\n')\n"
        "if 'describe-instances' in args:\n"
        "    instances = [{'InstanceId': 'i-0123456789abcdef0'}]\n"
        "    if os.environ.get('NO_TARGET'): instances = []\n"
        "    if os.environ.get('MULTIPLE_TARGETS'): instances *= 2\n"
        "    print(json.dumps({'Reservations': [{'Instances': instances}]}))\n"
        "elif 'describe-instance-information' in args:\n"
        "    print(json.dumps({'InstanceInformationList': [{'InstanceId': 'i-0123456789abcdef0', 'PingStatus': os.environ.get('PING', 'Online')}]}))\n"
        "elif 'send-command' in args:\n"
        "    payload = json.loads(pathlib.Path(args[args.index('--cli-input-json') + 1][7:]).read_text())\n"
        "    pathlib.Path(os.environ['PAYLOAD']).write_text(json.dumps(payload))\n"
        "    if os.environ.get('SEND_ERROR'):\n"
        "        print('connection lost', file=sys.stderr); sys.exit(1)\n"
        "    print(json.dumps({'Command': {'CommandId': 'example-command-id'}}))\n"
        "elif 'get-command-invocation' in args:\n"
        "    marker = pathlib.Path(os.environ['PAYLOAD'] + '.polled')\n"
        "    if os.environ.get('POLL_ERROR') and not marker.exists():\n"
        "        marker.touch()\n"
        "        print('An error occurred (' + os.environ['POLL_ERROR'] + ')', file=sys.stderr); sys.exit(1)\n"
        "    sequence = os.environ.get('STATUS_SEQUENCE', '').split(',')\n"
        "    count = int(marker.read_text()) if marker.exists() and marker.read_text() else 0\n"
        "    marker.write_text(str(count + 1))\n"
        "    status = sequence[min(count, len(sequence) - 1)] if sequence[0] else os.environ.get('STATUS', 'Success')\n"
        "    print(json.dumps({'Status': status, 'ResponseCode': int(os.environ.get('RESPONSE_CODE', '0')), 'StandardOutputContent': os.environ.get('REMOTE_OUTPUT', 'remote outcome')}))\n"
        "else: sys.exit(2)\n"
    )
    aws.chmod(0o755)
    log = tmp_path / "calls.jsonl"
    payload = tmp_path / "payload.json"
    environment = {
        **os.environ,
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "COMMAND_LOG": str(log),
        "PAYLOAD": str(payload),
    }

    def run(**changes):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--region",
                "eu-north-1",
                "--tag-value",
                "huginn-production",
                "--user",
                "ubuntu",
                "--path",
                "/home/ubuntu/Huginn",
                "--commit",
                COMMIT,
                "--image",
                IMAGE,
                "--wait-seconds",
                "1",
                "--poll-seconds",
                "0.01",
            ],
            env={**environment, **changes},
            capture_output=True,
            text=True,
            timeout=10,
        )

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()]

    return run, calls, payload


def test_dispatches_exact_commit_digest_and_source_as_checkout_owner(dispatcher):
    run, calls, payload = dispatcher
    result = run()
    assert result.returncode == 0, result.stderr
    request = json.loads(payload.read_text())
    assert request["InstanceIds"] == ["i-0123456789abcdef0"]
    assert request["DocumentName"] == "AWS-RunShellScript"
    assert request["Parameters"]["executionTimeout"] == ["900"]
    args = shlex.split(request["Parameters"]["commands"][0])
    assert args[:7] == ["sudo", "-n", "-H", "-u", "ubuntu", "python3", "-c"]
    assert args[8:] == ["/home/ubuntu/Huginn", COMMIT, IMAGE]
    encoded = re.search(r"b64decode\(([^)]+)\)", args[7]).group(1)
    assert base64.b64decode(ast.literal_eval(encoded)) == REMOTE_SCRIPT.read_bytes()
    assert sum("send-command" in call for call in calls()) == 1
    assert "example-command-id" in result.stdout


@pytest.mark.parametrize(
    "changes", [{"NO_TARGET": "1"}, {"MULTIPLE_TARGETS": "1"}, {"PING": "Offline"}]
)
def test_missing_ambiguous_or_offline_target_fails_without_sending(dispatcher, changes):
    run, calls, _ = dispatcher
    result = run(**changes)
    assert result.returncode != 0
    assert not any("send-command" in call for call in calls())


@pytest.mark.parametrize("status", ["Failed", "TimedOut", "Cancelled", "Cancelling"])
def test_remote_terminal_failure_is_not_reported_as_success(dispatcher, status):
    run, _, _ = dispatcher
    result = run(STATUS=status, RESPONSE_CODE="1")
    assert result.returncode != 0
    assert status in result.stderr


def test_success_status_with_nonzero_exit_code_fails(dispatcher):
    run, _, _ = dispatcher
    assert run(RESPONSE_CODE="1").returncode != 0


def test_eventual_consistency_retries_invocation_lookup_without_resending(dispatcher):
    run, calls, _ = dispatcher
    result = run(POLL_ERROR="InvocationDoesNotExist")
    assert result.returncode == 0, result.stderr
    assert sum("send-command" in call for call in calls()) == 1
    assert sum("get-command-invocation" in call for call in calls()) == 2


def test_other_polling_error_fails_without_retry_or_resend(dispatcher):
    run, calls, _ = dispatcher
    result = run(POLL_ERROR="AccessDeniedException")
    assert result.returncode != 0
    assert sum("get-command-invocation" in call for call in calls()) == 1
    assert sum("send-command" in call for call in calls()) == 1


def test_uncertain_send_is_not_resubmitted(dispatcher):
    run, calls, _ = dispatcher
    result = run(SEND_ERROR="1")
    assert result.returncode != 0
    assert sum("send-command" in call for call in calls()) == 1
    assert "not resent" in result.stderr


def test_poll_timeout_is_failure_and_does_not_resubmit(dispatcher):
    run, calls, _ = dispatcher
    result = run(STATUS="InProgress")
    assert result.returncode != 0
    assert "timed out" in result.stderr
    assert sum("send-command" in call for call in calls()) == 1


def test_pending_and_delayed_command_is_polled_until_success(dispatcher):
    run, calls, _ = dispatcher
    result = run(STATUS_SEQUENCE="Pending,Delayed,InProgress,Success")
    assert result.returncode == 0, result.stderr
    assert sum("get-command-invocation" in call for call in calls()) == 4
    assert sum("send-command" in call for call in calls()) == 1


def test_superseded_release_preserves_skip_message_without_claiming_deployment(
    dispatcher,
):
    run, _, _ = dispatcher
    result = run(
        REMOTE_OUTPUT="Skipping stale deployment: this commit is no longer master"
    )
    assert result.returncode == 0, result.stderr
    assert "Skipping stale deployment" in result.stdout
    assert "EC2 deployment succeeded" not in result.stdout
    assert "SSM command completed successfully" in result.stdout
