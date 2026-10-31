#!/usr/bin/env python3
"""Deploy an already published image to an existing EC2 Compose checkout."""

import fcntl
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def command(*arguments: str) -> str:
    # Capture output: Compose diagnostics can include private configuration.
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=600)
    if result.returncode:
        raise RuntimeError(f"Command failed: {' '.join(arguments[:4])}")
    return result.stdout.strip()


def replace_private_file(path: Path, content: bytes) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def deploy(checkout: Path, commit: str, image: str) -> None:
    os.chdir(checkout)
    private_config = checkout / ".env"
    if not private_config.is_file() or private_config.is_symlink():
        raise RuntimeError(
            "An existing private .env file is required; complete first setup"
        )
    if command("git", "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("Checkout has tracked changes; deployment stopped")
    command("git", "fetch", "--no-tags", "origin", "master:refs/remotes/origin/master")
    if command("git", "rev-parse", "origin/master") != commit:
        print("Skipping stale deployment: this commit is no longer master")
        return
    previous = command("git", "rev-parse", "HEAD")
    changes = command(
        "git",
        "diff",
        "--name-only",
        previous,
        commit,
        "--",
        "db/schema",
        "docker/postgres",
    ).splitlines()
    if any(path.endswith((".sql", ".sh")) for path in changes):
        raise RuntimeError(
            "Database schema/bootstrap changed; apply the documented schema upgrade "
            "and check out the published commit manually before retrying deployment"
        )
    command("sudo", "-n", "docker", "pull", image)
    revision = command(
        "sudo",
        "-n",
        "docker",
        "image",
        "inspect",
        image,
        "--format",
        '{{index .Config.Labels "org.opencontainers.image.revision"}}',
    )
    if revision != commit:
        raise RuntimeError(
            "Published image revision does not match the requested commit"
        )
    original = private_config.read_bytes()
    pattern = rb"(?m)^[ \t]*(?:export[ \t]+)?HUGINN_IMAGE[ \t]*=[^\r\n]*(?:\r?\n|$)"
    replacement = f"HUGINN_IMAGE={image}\n".encode()
    if re.search(pattern, original):
        updated = re.sub(pattern, lambda _: replacement, original)
    else:
        updated = original + (b"" if original.endswith(b"\n") else b"\n") + replacement
    changed_checkout = False
    try:
        command("git", "checkout", "--detach", commit)
        changed_checkout = True
        replace_private_file(private_config, updated)
        command("sudo", "-n", "docker", "compose", "pull")
        command(
            "sudo",
            "-n",
            "docker",
            "compose",
            "up",
            "-d",
            "--no-build",
            "--wait",
            "--wait-timeout",
            "180",
        )
        command(
            "sudo",
            "-n",
            "docker",
            "compose",
            "exec",
            "-T",
            "app",
            "python",
            "-c",
            "import urllib.request; "
            "urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=5)",
        )
    except Exception:
        print(
            "Deployment failed. Containers may have changed: inspect service state "
            "and recover using the deployment guide.",
            file=sys.stderr,
        )
        try:
            replace_private_file(private_config, original)
        finally:
            if changed_checkout:
                command("git", "checkout", "--detach", previous)
        print("Previous checkout and .env restored", file=sys.stderr)
        raise
    print(f"Deployed {commit}; application readiness check passed")


def main() -> int:
    try:
        if len(sys.argv) != 4:
            raise ValueError(
                "Expected deployment directory, commit SHA and image digest"
            )
        raw_checkout, commit, image = sys.argv[1:]
        if not re.fullmatch(r"/[A-Za-z0-9_./-]+", raw_checkout):
            raise ValueError(
                "Deployment directory must be an absolute path without spaces"
            )
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Expected a full commit SHA")
        if not re.fullmatch(r"ghcr\.io/[a-z0-9_./-]+@sha256:[0-9a-f]{64}", image):
            raise ValueError("Expected an immutable GHCR image digest")
        checkout = Path(raw_checkout).resolve(strict=True)
        state = checkout / ".local-runtime"
        state.mkdir(mode=0o700, exist_ok=True)
        with (state / "ec2-deployment.lock").open("w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError(
                    "Another deployment holds the host lock; retry later"
                ) from exc
            deploy(checkout, commit, image)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"Deployment failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
