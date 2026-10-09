"""Loopback-only browser mail fixture with actual SMTP and delivery policy."""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from email import message_from_bytes, policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet

from huginn.management.application.requests.deliver_lifecycle_mail_request import (
    DeliverLifecycleMailRequest,
)
from huginn.management.config import ManagementConfig
from huginn.management.presentation.cli.lifecycle_mail_worker import _build_service
from tests.management.test_lifecycle_smtp import _smtp_sink


@contextmanager
def browser_lifecycle_mail(config: ManagementConfig) -> Iterator[ManagementConfig]:
    with _smtp_sink() as smtp:
        resolved = replace(
            config,
            lifecycle_proof_key=Fernet.generate_key().decode(),
            web_origin=f"http://127.0.0.1:{os.environ.get('HUGINN_BROWSER_PORT', '4173')}",
            smtp_host="127.0.0.1",
            smtp_port=smtp.server_address[1],
        )

        class MailView(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                url = urlsplit(self.path)
                if url.path != "/messages":
                    self.send_error(404)
                    return
                recipient = parse_qs(url.query).get("recipient", [None])[0]
                messages = []
                for raw in list(smtp.messages):
                    message = message_from_bytes(raw, policy=policy.default)
                    if recipient is None or message["To"] == recipient:
                        messages.append(
                            {
                                "recipient": str(message["To"]),
                                "text": message.get_content(),
                            }
                        )
                payload = json.dumps(messages).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        mailbox = ThreadingHTTPServer(
            ("127.0.0.1", int(os.environ.get("HUGINN_BROWSER_MAIL_PORT", "8025"))),
            MailView,
        )
        mailbox_thread = Thread(target=mailbox.serve_forever, daemon=True)
        stopping = Event()
        failures: list[str] = []
        service = _build_service(resolved)

        def dispatch():
            try:
                while not stopping.is_set():
                    result = service.execute(DeliverLifecycleMailRequest())
                    if result.outcome == "idle":
                        stopping.wait(0.1)
            except Exception as exc:
                failures.append(type(exc).__name__)

        worker = Thread(target=dispatch, daemon=True)
        mailbox_thread.start()
        worker.start()
        try:
            yield resolved
        finally:
            stopping.set()
            worker.join(timeout=35)
            mailbox.shutdown()
            mailbox.server_close()
            mailbox_thread.join(timeout=5)
            if worker.is_alive() or failures:
                raise RuntimeError("browser lifecycle mail fixture failed")
