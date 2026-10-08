"""Same-origin browser auth mutations, preserving trusted operator clients."""

from urllib.parse import urlsplit

from fastapi import Request

from huginn.management.application.errors.errors import AuthorizationError


def _origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            return None
        return (
            parsed.scheme,
            parsed.hostname,
            parsed.port
            if parsed.port is not None
            else (443 if parsed.scheme == "https" else 80),
        )
    except ValueError:
        return None


def require_same_origin_browser_mutation(request: Request) -> None:
    """Compare the browser origin with the request origin, never forwarded headers."""
    content_type = (
        request.headers.get("content-type", "").partition(";")[0].strip().lower()
    )
    fetch_site = request.headers.get("sec-fetch-site")
    origin = request.headers.get("origin")
    if content_type != "application/json" or (
        fetch_site is not None and fetch_site.lower() not in {"same-origin", "none"}
    ):
        raise AuthorizationError("same-origin JSON request is required")
    if origin is not None:
        supplied = _origin(origin)
        expected = _origin(f"{request.url.scheme}://{request.url.netloc}")
        if supplied is None or supplied != expected:
            raise AuthorizationError("same-origin JSON request is required")
