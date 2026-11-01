"""Create private Compose secrets, or add admin credentials to an older config."""

import argparse
import base64
import fcntl
import ipaddress
import json
import os
import re
import secrets
import subprocess
from pathlib import Path


def validate_https_configuration(config: dict) -> str | None:
    """Validate resolved ingress settings; see the HTTPS operator guide."""
    services = config.get("services", {})
    if "traefik" not in services:
        return None
    proxy = services["traefik"]
    values = proxy.get("environment", {})
    domain = values.get("HUGINN_DOMAIN", "")
    alias = values.get("HUGINN_DOMAIN_ALIAS", "")
    hostname = re.compile(
        r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z"
    )
    for key, value in (("HUGINN_DOMAIN", domain), ("HUGINN_DOMAIN_ALIAS", alias)):
        if not hostname.fullmatch(value):
            raise ValueError(f"{key} must be a lowercase DNS hostname")
    if domain == alias:
        raise ValueError("HUGINN_DOMAIN_ALIAS must differ from HUGINN_DOMAIN")
    if not re.fullmatch(
        r"[^\s@]+@[^\s@]+\.[^\s@]+", values.get("HUGINN_ACME_EMAIL", "")
    ):
        raise ValueError("HUGINN_ACME_EMAIL must contain a contact email address")
    if values.get("HUGINN_ACME_ENVIRONMENT") not in {"production", "staging"}:
        raise ValueError("HUGINN_ACME_ENVIRONMENT must be production or staging")
    app = services.get("app", {})
    environment = app.get("environment", {})
    if environment.get("HUGINN_WEB_ORIGIN") != f"https://{domain}":
        raise ValueError("HUGINN_WEB_ORIGIN must equal the canonical HTTPS origin")
    if environment.get("HUGINN_MANAGEMENT_ENVIRONMENT") != "production":
        raise ValueError("HUGINN_MANAGEMENT_ENVIRONMENT must be production")
    ports = app.get("ports", [])
    if not ports or any(
        port.get("host_ip") not in {"127.0.0.1", "::1"} for port in ports
    ):
        raise ValueError("HUGINN_BIND_ADDRESS must bind the app to loopback")
    try:
        address = ipaddress.ip_address(values.get("HUGINN_PROXY_IP", ""))
        network = ipaddress.ip_network(
            config["networks"]["ingress"]["ipam"]["config"][0]["subnet"]
        )
        private_ranges = tuple(
            ipaddress.ip_network(value)
            for value in (
                "10.0.0.0/8",
                "172.16.0.0/12",
                "192.168.0.0/16",
            )
        )
        gateway = ipaddress.ip_address(
            config["networks"]["ingress"]["ipam"]["config"][0].get(
                "gateway", str(network.network_address + 1)
            )
        )
        if (
            address.version != 4
            or network.version != 4
            or network.prefixlen != 29
            or not any(network.subnet_of(private) for private in private_ranges)
            or address not in network
            or address in {network.network_address, network.broadcast_address, gateway}
        ):
            raise ValueError
    except (ValueError, KeyError, IndexError):
        raise ValueError(
            "HUGINN_PROXY_IP and HUGINN_INGRESS_SUBNET must specify a private address in a narrow IPv4 ingress network"
        ) from None
    if environment.get("FORWARDED_ALLOW_IPS") != str(address) or proxy.get(
        "networks", {}
    ).get("ingress", {}).get("ipv4_address") != str(address):
        raise ValueError(
            "HUGINN_PROXY_IP must be the only trusted forwarding address and match the ingress address"
        )
    for name, service in services.items():
        if name not in {"app", "traefik"} and "ingress" in service.get("networks", {}):
            raise ValueError("Only app and traefik may attach to the ingress network")
    return domain


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / ".env")
    parser.add_argument(
        "--add-admin",
        action="store_true",
        help="add missing admin credentials without changing other settings",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the resolved Compose configuration without writing settings",
    )
    args = parser.parse_args()
    if args.check:
        if args.add_admin:
            parser.error("--check cannot be combined with --add-admin")
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(args.output),
                "-f",
                str(root / "compose.yaml"),
                "config",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            parser.exit(
                1,
                "Compose configuration could not be resolved; check the private settings.\n",
            )
        try:
            domain = validate_https_configuration(json.loads(result.stdout))
        except (ValueError, TypeError, KeyError) as error:
            parser.exit(1, f"Invalid Compose configuration: {error}\n")
        print(json.dumps({"https": domain is not None, "domain": domain}))
        return 0
    content = (root / "compose.env.example").read_text()
    content = content.replace(
        "POSTGRES_PASSWORD=\n", f"POSTGRES_PASSWORD={secrets.token_hex(24)}\n"
    )
    key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    content = content.replace(
        "HUGINN_LIFECYCLE_PROOF_KEY=\n", f"HUGINN_LIFECYCLE_PROOF_KEY={key}\n"
    )
    prefixes = ("HUGINN_BOOTSTRAP_ADMIN", "HUGINN_BOOTSTRAP_SECOND_ADMIN")
    passwords = set()
    for prefix in prefixes:
        password = secrets.token_urlsafe(9) + "A1!"
        while password in passwords:
            password = secrets.token_urlsafe(9) + "A1!"
        passwords.add(password)
        content = content.replace(
            f"{prefix}_PASSWORD=\n", f"{prefix}_PASSWORD={password}\n"
        )
    if args.add_admin:
        fd = os.open(args.output, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW)
        with os.fdopen(fd, "r+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            existing = stream.read()
            values = {
                line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
                for line in existing.splitlines()
                if "=" in line and not line.lstrip().startswith("#")
            }
            missing = []
            for prefix in prefixes:
                required = {
                    f"{prefix}_{field}" for field in ("USERNAME", "EMAIL", "PASSWORD")
                }
                present = required & values.keys()
                if present and (
                    present != required or any(not values[key] for key in required)
                ):
                    parser.exit(
                        1,
                        "Partial admin configuration exists; complete it explicitly.\n",
                    )
                if not present:
                    missing.append(prefix)
            if not missing:
                print("Admin configuration already exists; preserving it.")
                return 0
            os.fchmod(stream.fileno(), 0o600)
            admin_lines = [
                line
                for line in content.splitlines()
                if any(line.startswith(prefix + "_") for prefix in missing)
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
