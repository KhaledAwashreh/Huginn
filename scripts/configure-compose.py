"""Create private Compose secrets, or add admin credentials to an older config."""

import argparse
import base64
import fcntl
import os
import secrets
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / ".env")
    parser.add_argument(
        "--add-admin",
        action="store_true",
        help="add missing admin credentials without changing other settings",
    )
    args = parser.parse_args()
    content = (root / "compose.env.example").read_text()
    content = content.replace(
        "POSTGRES_PASSWORD=\n", f"POSTGRES_PASSWORD={secrets.token_hex(24)}\n"
    )
    key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    content = content.replace(
        "HUGINN_LIFECYCLE_PROOF_KEY=\n", f"HUGINN_LIFECYCLE_PROOF_KEY={key}\n"
    )
    admin_password = secrets.token_urlsafe(9) + "A1!"
    content = content.replace(
        "HUGINN_BOOTSTRAP_ADMIN_PASSWORD=\n",
        f"HUGINN_BOOTSTRAP_ADMIN_PASSWORD={admin_password}\n",
    )
    if args.add_admin:
        fd = os.open(args.output, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW)
        with os.fdopen(fd, "r+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            existing = stream.read()
            keys = {
                line.split("=", 1)[0].strip()
                for line in existing.splitlines()
                if "=" in line and not line.lstrip().startswith("#")
            }
            required = {
                "HUGINN_BOOTSTRAP_ADMIN_USERNAME",
                "HUGINN_BOOTSTRAP_ADMIN_EMAIL",
                "HUGINN_BOOTSTRAP_ADMIN_PASSWORD",
            }
            if required <= keys:
                print("Admin configuration already exists; preserving it.")
                return 0
            if required & keys:
                parser.exit(
                    1, "Partial admin configuration exists; complete it explicitly.\n"
                )
            os.fchmod(stream.fileno(), 0o600)
            admin_lines = [
                line
                for line in content.splitlines()
                if line.startswith("HUGINN_BOOTSTRAP_ADMIN_")
            ]
            stream.write("\n" + "\n".join(admin_lines) + "\n")
        print(f"Added private admin configuration to {args.output}.")
        return 0
    try:
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.exit(1, "Configuration already exists; preserving existing secrets.\n")
    with os.fdopen(fd, "w") as stream:
        stream.write(content)
    print(f"Created {args.output}. Keep it private and reuse it across restarts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
