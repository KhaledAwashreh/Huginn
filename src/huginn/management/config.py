"""Management runtime configuration defined by ADR-0011."""

import os
import re
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

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

    def __post_init__(self) -> None:
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
