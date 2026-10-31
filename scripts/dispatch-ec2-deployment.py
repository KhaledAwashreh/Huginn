#!/usr/bin/env python3
"""Dispatch the checked-in deployment entry point through AWS Systems Manager."""

import argparse
import base64
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path


class AwsCommandError(RuntimeError):
    def __init__(self, operation: str, stderr: str) -> None:
        super().__init__(f"AWS {operation} failed")
        self.invocation_not_found = "(InvocationDoesNotExist)" in stderr


def aws(region: str, service: str, operation: str, *arguments: str) -> dict:
    result = subprocess.run(
        [
            "aws",
            "--region",
            region,
            "--output",
            "json",
            "--no-cli-pager",
            service,
            operation,
            *arguments,
        ],
        capture_output=True,
        text=True,
        timeout=45,
        env={**os.environ, "AWS_MAX_ATTEMPTS": "1", "AWS_RETRY_MODE": "standard"},
    )
    if result.returncode:
        raise AwsCommandError(operation, result.stderr)
    return json.loads(result.stdout)


def dispatch(arguments: argparse.Namespace) -> None:
    instances = aws(
        arguments.region,
        "ec2",
        "describe-instances",
        "--filters",
        f"Name=tag:HuginnDeployment,Values={arguments.tag_value}",
        "Name=instance-state-name,Values=running",
    )
    targets = [
        instance["InstanceId"]
        for reservation in instances.get("Reservations", [])
        for instance in reservation.get("Instances", [])
    ]
    if len(targets) != 1 or not re.fullmatch(r"i-[0-9a-f]{8,17}", targets[0]):
        raise RuntimeError(
            "Expected exactly one running EC2 instance with the deployment tag"
        )
    instance_id = targets[0]
    managed = aws(
        arguments.region,
        "ssm",
        "describe-instance-information",
        "--filters",
        f"Key=InstanceIds,Values={instance_id}",
    ).get("InstanceInformationList", [])
    if not any(
        item.get("InstanceId") == instance_id and item.get("PingStatus") == "Online"
        for item in managed
    ):
        raise RuntimeError("The target instance is not online in Systems Manager")
    source = Path(__file__).with_name("deploy-ec2.py").read_bytes()
    encoded = base64.b64encode(source).decode("ascii")
    bootstrap = (
        f"import base64;exec(compile(base64.b64decode({encoded!r}),"
        "'deploy-ec2.py','exec'))"
    )
    remote_command = shlex.join(
        [
            "sudo",
            "-n",
            "-H",
            "-u",
            arguments.user,
            "python3",
            "-c",
            bootstrap,
            arguments.path,
            arguments.commit,
            arguments.image,
        ]
    )
    if len(remote_command.encode()) > 60_000:
        raise RuntimeError("Deployment command exceeds the bounded SSM command size")
    payload = {
        "DocumentName": "AWS-RunShellScript",
        "InstanceIds": [instance_id],
        "TimeoutSeconds": 60,
        "Comment": f"Huginn deploy {arguments.commit}",
        "Parameters": {"commands": [remote_command], "executionTimeout": ["900"]},
    }
    with tempfile.TemporaryDirectory(prefix="huginn-ssm-") as directory:
        request = Path(directory) / "request.json"
        request.write_text(json.dumps(payload))
        try:
            sent = aws(
                arguments.region,
                "ssm",
                "send-command",
                "--cli-input-json",
                f"file://{request}",
            )
        except (RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
            raise RuntimeError(
                "SendCommand outcome is uncertain; command was not resent. Inspect "
                "Systems Manager command history before retrying this workflow."
            ) from exc
    command_id = sent.get("Command", {}).get("CommandId")
    if not isinstance(command_id, str) or not command_id:
        raise RuntimeError(
            "SendCommand returned no command ID; inspect command history before retrying"
        )
    print(f"SSM command {command_id} on {instance_id}", flush=True)
    deadline = time.monotonic() + arguments.wait_seconds
    while time.monotonic() < deadline:
        try:
            result = aws(
                arguments.region,
                "ssm",
                "get-command-invocation",
                "--command-id",
                command_id,
                "--instance-id",
                instance_id,
            )
        except AwsCommandError as exc:
            if not exc.invocation_not_found:
                raise
        else:
            status = result.get("Status")
            if status == "Success" and result.get("ResponseCode") == 0:
                print(result.get("StandardOutputContent", ""))
                print("SSM command completed successfully")
                return
            if status not in {"Pending", "InProgress", "Delayed"}:
                print(result.get("StandardOutputContent", ""))
                print(result.get("StandardErrorContent", ""), file=sys.stderr)
                raise RuntimeError(f"SSM deployment ended with status {status}")
        time.sleep(min(arguments.poll_seconds, max(0, deadline - time.monotonic())))
    raise RuntimeError(
        f"Waiting for SSM command {command_id} timed out; command was not resent. "
        "Inspect its status before retrying; server execution is bounded to 900 seconds."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("region", "tag-value", "user", "path", "commit", "image"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--wait-seconds", type=float, default=1020)
    parser.add_argument("--poll-seconds", type=float, default=5)
    arguments = parser.parse_args()
    patterns = {
        "region": r"[a-z]{2}(?:-[a-z]+)+-[0-9]",
        "tag_value": r"[A-Za-z0-9_.-]+",
        "user": r"[a-z_][a-z0-9_-]*",
        "path": r"/[A-Za-z0-9_./-]+",
        "commit": r"[0-9a-f]{40}",
        "image": r"ghcr\.io/[a-z0-9_./-]+@sha256:[0-9a-f]{64}",
    }
    try:
        if any(
            not re.fullmatch(pattern, getattr(arguments, name))
            for name, pattern in patterns.items()
        ):
            raise ValueError("Invalid deployment arguments")
        if not (
            0 < arguments.wait_seconds <= 1080 and 0 < arguments.poll_seconds <= 30
        ):
            raise ValueError("Invalid deployment polling limits")
        dispatch(arguments)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"Deployment failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
