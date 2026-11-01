"""Exercise resolved Compose resolver selection with both persisted certificate stores."""

import os
import re
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from fastapi import FastAPI

from tests.https_proxy_harness import ROOT, _test_certificate, real_https_proxy


@pytest.mark.parametrize(
    "selected,expected_authority",
    [
        ("production", "https://acme-v02.api.letsencrypt.org/directory"),
        ("staging", "https://acme-staging-v02.api.letsencrypt.org/directory"),
    ],
)
def test_selected_entrypoint_uses_only_matching_literal_authority(
    tmp_path, selected, expected_authority
):
    executable = tmp_path / "traefik"
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    executable.chmod(0o755)
    result = subprocess.run(
        ["/bin/sh", str(ROOT / "docker/traefik/start.sh"), "--ping=true"],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:/usr/bin:/bin",
            "HUGINN_ACME_ENVIRONMENT": selected,
            "HUGINN_ACME_EMAIL": "owner@example.test",
        },
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    flags = result.stdout.splitlines()
    assert (
        f"--certificatesresolvers.{selected}.acme.caserver={expected_authority}"
        in flags
    )
    assert (
        f"--certificatesresolvers.{selected}.acme.storage=/certificates/{selected}/acme.json"
        in flags
    )
    assert {
        match.group(1)
        for flag in flags
        if (match := re.match(r"--certificatesresolvers\.([^.]+)\.", flag))
    } == {selected}


def test_selected_entrypoint_rejects_unknown_environment_before_starting():
    result = subprocess.run(
        ["/bin/sh", str(ROOT / "docker/traefik/start.sh")],
        env={**os.environ, "HUGINN_ACME_ENVIRONMENT": "unexpected"},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode != 0
    assert "HUGINN_ACME_ENVIRONMENT must be production or staging" in result.stderr


@pytest.fixture
def failed_local_authority(tmp_path):
    requests = []

    class Authority(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(503)
            self.end_headers()

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Authority)
    certificates = tmp_path / "authority"
    certificates.mkdir()
    _test_certificate(certificates)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificates / "cert.pem", certificates / "key.pem")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            f"https://127.0.0.1:{server.server_port}/directory",
            requests,
            certificates / "ca.pem",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _app():
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


@pytest.mark.parametrize(
    "selected,other", [("production", "staging"), ("staging", "production")]
)
def test_other_environment_certificate_cannot_suppress_selected_issuance(
    tmp_path,
    failed_local_authority,
    selected,
    other,
):
    authority, requests, authority_ca = failed_local_authority
    with real_https_proxy(
        _app(),
        tmp_path / "proxy",
        selected=selected,
        seeded=(other,),
        authority=authority,
        authority_ca=authority_ca,
        require_trusted=False,
    ) as proxy:
        other_certificate = x509.load_pem_x509_certificate(
            (proxy.directory / "cert.pem").read_bytes()
        )
        assert proxy.certificate_fingerprint() != other_certificate.fingerprint(
            hashes.SHA256()
        )
        deadline = time.monotonic() + 8
        while not requests and time.monotonic() < deadline:
            time.sleep(0.05)
        logs = subprocess.run(
            ["docker", "logs", proxy.container],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert requests, (
            "selected environment must attempt issuance: " + logs.stdout + logs.stderr
        )
        assert all(path == "/directory" for path in requests)


@pytest.mark.parametrize("selected", ["production", "staging"])
def test_only_selected_resolver_loads_when_both_certificate_stores_exist(
    tmp_path, selected
):
    with real_https_proxy(
        _app(),
        tmp_path / "proxy",
        selected=selected,
        seeded=("production", "staging"),
        require_trusted=False,
    ) as proxy:
        result = subprocess.run(
            ["docker", "exec", proxy.container, "cat", "/proc/1/cmdline"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        active = set(re.findall(r"--certificatesresolvers\.([^.]+)\.", result.stdout))
        assert active == {selected}
        selected_certificate = x509.load_pem_x509_certificate(
            (proxy.directory / "cert.pem").read_bytes()
        )
        assert proxy.certificate_fingerprint() == selected_certificate.fingerprint(
            hashes.SHA256()
        )
        assert proxy.request("/health")[0] == 200
        other = "staging" if selected == "production" else "production"
        other_state = proxy.directory / f"state/{other}/acme.json"
        original_other_state = other_state.read_bytes()
        proxy.recreate()
        assert proxy.certificate_fingerprint() == selected_certificate.fingerprint(
            hashes.SHA256()
        )
        assert other_state.read_bytes() == original_other_state
