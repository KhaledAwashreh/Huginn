"""Real ingress test infrastructure; all listeners and certificate keys are disposable."""

import base64
import contextlib
import ipaddress
import json
import re
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]


def _free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _test_certificate(directory):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Huginn test CA")])
    now = datetime.now(UTC)
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=90))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=90))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.DNSName("alias.localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    for filename, data in (
        ("ca.pem", ca.public_bytes(serialization.Encoding.PEM)),
        ("cert.pem", leaf.public_bytes(serialization.Encoding.PEM)),
        (
            "key.pem",
            leaf_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        ),
    ):
        path = directory / filename
        path.write_bytes(data)
        path.chmod(0o600)


@dataclass
class HttpsProxy:
    directory: Path
    http_port: int
    https_port: int
    container: str
    run_command: tuple[str, ...] = ()

    @property
    def origin(self):
        return f"https://localhost:{self.https_port}"

    def recreate(self):
        subprocess.run(
            ["docker", "rm", "--force", self.container],
            capture_output=True,
            check=True,
            timeout=10,
        )
        subprocess.run(self.run_command, capture_output=True, check=True, timeout=30)
        deadline = time.monotonic() + 15
        while True:
            try:
                if self.request("/health")[0] == 200:
                    return
            except subprocess.CalledProcessError, subprocess.TimeoutExpired:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("recreated proxy failed TLS readiness")
            time.sleep(0.1)

    def request(
        self,
        path,
        *,
        method="GET",
        headers=None,
        data=None,
        host="localhost",
        https=True,
    ):
        port = self.https_port if https else self.http_port
        command = [
            "curl",
            "--silent",
            "--show-error",
            "--noproxy",
            "*",
            "--max-time",
            "8",
            "--cacert",
            str(self.directory / "ca.pem"),
            "--resolve",
            f"{host}:{port}:127.0.0.1",
            "--request",
            method,
            "--dump-header",
            str(self.directory / "headers"),
            "--cookie",
            str(self.directory / "cookies"),
            "--cookie-jar",
            str(self.directory / "cookies"),
        ]
        for key, value in (headers or {}).items():
            command.extend(["--header", f"{key}: {value}"])
        if data is not None:
            command.extend(
                [
                    "--header",
                    "Content-Type: application/json",
                    "--data",
                    json.dumps(data),
                ]
            )
        command.append(f"{'https' if https else 'http'}://{host}:{port}{path}")
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=10, check=True
        )
        raw = (self.directory / "headers").read_text()
        status = int(raw.splitlines()[0].split()[1])
        response_headers = {
            key.lower(): value.strip()
            for line in raw.splitlines()[1:]
            if ":" in line
            for key, value in [line.split(":", 1)]
        }
        return status, response_headers, result.stdout


@contextlib.contextmanager
def real_https_proxy(app, directory):
    """Use production file-provider routes, with only local TLS/upstream substitutions."""
    directory.mkdir(parents=True, exist_ok=True)
    _test_certificate(directory)
    upstream_port, http_port, https_port = (_free_port() for _ in range(3))
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=upstream_port,
            proxy_headers=True,
            forwarded_allow_ips="127.0.0.1",
            log_level="error",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("disposable upstream failed to start")
        time.sleep(0.05)
    name = f"huginn-https-test-{uuid4().hex}"
    try:
        source = ROOT / "docker/traefik/dynamic.yaml"
        routes = source.read_text().replace(
            "http://app:8000", f"http://127.0.0.1:{upstream_port}"
        )
        # Seed a local-CA certificate in Traefik's actual persistent ACME format.
        # Issuance/renewal remains separate; a loopback-only CA URL prevents live requests.
        state = directory / "state"
        state.mkdir(mode=0o700)
        storage = state / "acme.json"
        storage.write_text(
            json.dumps(
                {
                    "production": {
                        "Certificates": [
                            {
                                "domain": {
                                    "main": "localhost",
                                    "sans": ["alias.localhost"],
                                },
                                "certificate": base64.b64encode(
                                    (directory / "cert.pem").read_bytes()
                                ).decode(),
                                "key": base64.b64encode(
                                    (directory / "key.pem").read_bytes()
                                ).decode(),
                                "Store": "default",
                            }
                        ]
                    }
                }
            )
        )
        storage.chmod(0o600)
        (directory / "dynamic.yaml").write_text(routes)
        image = re.search(
            r"image: (traefik:[^\s]+)", (ROOT / "compose.yaml").read_text()
        ).group(1)
        run_command = [
            "docker",
            "run",
            "--detach",
            "--name",
            name,
            "--network",
            "host",
            "--volume",
            f"{directory}:/config:ro",
            "--volume",
            f"{state}:/state",
            "--env",
            "HUGINN_DOMAIN=localhost",
            "--env",
            "HUGINN_DOMAIN_ALIAS=alias.localhost",
            "--env",
            "HUGINN_ACME_ENVIRONMENT=production",
            image,
            f"--entrypoints.web.address=127.0.0.1:{http_port}",
            f"--entrypoints.websecure.address=127.0.0.1:{https_port}",
            "--providers.file.directory=/config",
            "--certificatesresolvers.production.acme.email=test@example.test",
            "--certificatesresolvers.production.acme.storage=/state/acme.json",
            "--certificatesresolvers.production.acme.caserver=https://127.0.0.1:1/directory",
            "--certificatesresolvers.production.acme.httpchallenge.entrypoint=web",
            "--log.level=ERROR",
        ]
        subprocess.run(
            run_command,
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        proxy = HttpsProxy(directory, http_port, https_port, name, tuple(run_command))
        deadline = time.monotonic() + 15
        while True:
            try:
                if proxy.request("/health")[0] == 200:
                    break
            except subprocess.CalledProcessError, subprocess.TimeoutExpired:
                pass
            if time.monotonic() > deadline:
                logs = subprocess.run(
                    ["docker", "logs", name], capture_output=True, text=True, timeout=5
                )
                raise RuntimeError(
                    f"disposable HTTPS proxy failed: {logs.stdout}{logs.stderr}"
                )
            time.sleep(0.1)
        yield proxy
    finally:
        subprocess.run(
            ["docker", "rm", "--force", name], capture_output=True, timeout=10
        )
        server.should_exit = True
        thread.join(timeout=5)
