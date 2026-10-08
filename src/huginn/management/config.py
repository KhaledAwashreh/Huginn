"""Management runtime configuration defined by ADR-0011."""

import os
import re
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from dotenv import load_dotenv

from huginn.management.application.authentication_policy import SESSION_TTL_SECONDS
from huginn.management.presentation.api.constants.http import (
    DEFAULT_COOKIE_SAMESITE,
    DEFAULT_SESSION_COOKIE_NAME,
)


@dataclass(frozen=True)
class ManagementConfig:
    """Management process configuration defined by ADR-0011."""

    database_url: str = field(repr=False)
    cookie_name: str = DEFAULT_SESSION_COOKIE_NAME
    cookie_secure: bool | None = None
    cookie_samesite: str = DEFAULT_COOKIE_SAMESITE
    session_ttl: timedelta = timedelta(seconds=SESSION_TTL_SECONDS)
    login_throttle_failures: int = 5
    login_throttle_window: timedelta = timedelta(minutes=15)
    environment: str = "local"
    frontend_assets_path: Path | None = None
    lifecycle_proof_key: str | None = field(default=None, repr=False)
    web_origin: str | None = None
    verification_ttl_seconds: int = 86400
    reset_ttl_seconds: int = 1800
    receipt_username_limit: int = 5
    receipt_email_limit: int = 5
    receipt_ip_limit: int = 20
    proof_ip_limit: int = 10
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_tls: str = "none"
    smtp_sender: str = field(default="no-reply@huginn.local", repr=False)
    smtp_username: str | None = field(default=None, repr=False)
    smtp_password: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.lifecycle_proof_key is not None:
            try:
                Fernet(self.lifecycle_proof_key)
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid lifecycle encryption key") from exc
        if self.web_origin is not None:
            try:
                origin = urlsplit(self.web_origin)
                valid_port = origin.port
            except ValueError as exc:
                raise ValueError("invalid trusted web origin") from exc
            if (
                origin.scheme not in {"http", "https"}
                or not origin.hostname
                or origin.username is not None
                or origin.password is not None
                or origin.path not in {"", "/"}
                or origin.query
                or origin.fragment
                or valid_port == 0
            ):
                raise ValueError("invalid trusted web origin")
            if (
                self.environment in {"production", "staging"}
                and origin.scheme != "https"
            ):
                raise ValueError("trusted web origin requires HTTPS")
            object.__setattr__(self, "web_origin", self.web_origin.rstrip("/"))
        for value, maximum in (
            (self.verification_ttl_seconds, 604800),
            (self.reset_ttl_seconds, 86400),
            (self.receipt_username_limit, 1000),
            (self.receipt_email_limit, 1000),
            (self.receipt_ip_limit, 10000),
            (self.proof_ip_limit, 1000),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("invalid lifecycle policy setting")
        if type(self.smtp_port) is not int or not 1 <= self.smtp_port <= 65535:
            raise ValueError("invalid SMTP port")
        if self.smtp_tls not in {"none", "starttls", "implicit"}:
            raise ValueError("invalid SMTP TLS setting")
        if not self.smtp_host or any(
            character in self.smtp_host for character in "\r\n"
        ):
            raise ValueError("invalid SMTP host")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+", self.smtp_sender):
            raise ValueError("invalid SMTP sender")
        if self.cookie_secure is not None and not isinstance(self.cookie_secure, bool):
            raise ValueError("cookie Secure setting must be a boolean")
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", self.cookie_name):
            raise ValueError("invalid management cookie name")
        if self.cookie_samesite not in {"Strict", "Lax", "None"}:
            raise ValueError("cookie SameSite must be Strict, Lax, or None")
        if self.session_ttl <= timedelta(0):
            raise ValueError("session TTL must be positive")
        if self.login_throttle_failures < 1:
            raise ValueError("login throttle failures must be positive")
        if self.login_throttle_window <= timedelta(0):
            raise ValueError("login throttle window must be positive")
        if self.environment not in {
            "local",
            "development",
            "test",
            "staging",
            "production",
        }:
            raise ValueError("invalid management environment")
        secure = self.cookie_secure
        if secure is None:
            secure = self.environment not in {"local", "development", "test"}
        if self.environment in {"staging", "production"} and not secure:
            raise ValueError("Secure cookies are required outside local development")
        if self.cookie_samesite == "None" and not secure:
            raise ValueError("SameSite=None cookies require Secure")
        object.__setattr__(self, "cookie_secure", secure)


def load_config() -> ManagementConfig:
    """Load the isolated management configuration defined by ADR-0011."""
    load_dotenv()
    database_url = os.environ.get("HUGINN_MANAGEMENT_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("HUGINN_MANAGEMENT_DATABASE_URL is not set")
    environment = (
        os.environ.get("HUGINN_MANAGEMENT_ENVIRONMENT", "local").strip().lower()
    )
    try:
        ttl_seconds = int(
            os.environ.get(
                "HUGINN_MANAGEMENT_SESSION_TTL_SECONDS", str(SESSION_TTL_SECONDS)
            )
        )
        throttle_failures = int(
            os.environ.get("HUGINN_MANAGEMENT_LOGIN_THROTTLE_FAILURES", "5")
        )
        throttle_window_seconds = int(
            os.environ.get("HUGINN_MANAGEMENT_LOGIN_THROTTLE_WINDOW_SECONDS", "900")
        )
        return ManagementConfig(
            database_url=database_url,
            lifecycle_proof_key=os.environ.get("HUGINN_LIFECYCLE_PROOF_KEY") or None,
            web_origin=os.environ.get("HUGINN_WEB_ORIGIN") or None,
            verification_ttl_seconds=int(
                os.environ.get("HUGINN_VERIFICATION_TTL_SECONDS", "86400")
            ),
            reset_ttl_seconds=int(os.environ.get("HUGINN_RESET_TTL_SECONDS", "1800")),
            receipt_email_limit=int(os.environ.get("HUGINN_RECEIPT_EMAIL_LIMIT", "5")),
            receipt_username_limit=int(
                os.environ.get("HUGINN_RECEIPT_USERNAME_LIMIT", "5")
            ),
            receipt_ip_limit=int(os.environ.get("HUGINN_RECEIPT_IP_LIMIT", "20")),
            proof_ip_limit=int(os.environ.get("HUGINN_PROOF_IP_LIMIT", "10")),
            smtp_host=os.environ.get("HUGINN_SMTP_HOST", "localhost"),
            smtp_port=int(os.environ.get("HUGINN_SMTP_PORT", "1025")),
            smtp_tls=os.environ.get("HUGINN_SMTP_TLS", "none"),
            smtp_sender=os.environ.get("HUGINN_SMTP_SENDER", "no-reply@huginn.local"),
            smtp_username=os.environ.get("HUGINN_SMTP_USERNAME") or None,
            smtp_password=os.environ.get("HUGINN_SMTP_PASSWORD") or None,
            cookie_name=os.environ.get(
                "HUGINN_MANAGEMENT_COOKIE_NAME", DEFAULT_SESSION_COOKIE_NAME
            ).strip(),
            cookie_samesite=os.environ.get(
                "HUGINN_MANAGEMENT_COOKIE_SAMESITE", DEFAULT_COOKIE_SAMESITE
            ).strip(),
            session_ttl=timedelta(seconds=ttl_seconds),
            login_throttle_failures=throttle_failures,
            login_throttle_window=timedelta(seconds=throttle_window_seconds),
            environment=environment,
            frontend_assets_path=(
                Path(value)
                if (value := os.environ.get("HUGINN_FRONTEND_ASSETS_PATH", "").strip())
                else None
            ),
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError("invalid management configuration") from exc
