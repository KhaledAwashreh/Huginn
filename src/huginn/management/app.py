"""Management HTTP boundary defined by ADR-0011."""

from flask import Flask, Response, jsonify

from huginn.management.config import ManagementConfig, load_config
from huginn.management.database import PostgresReadiness
from huginn.management.ports import ReadinessPort


def create_app(
    config: ManagementConfig | None = None,
    *,
    readiness: ReadinessPort | None = None,
) -> Flask:
    """Create the inert management application defined by ADR-0011."""
    resolved_config = config if config is not None else load_config()
    probe = (
        readiness
        if readiness is not None
        else PostgresReadiness(resolved_config.database_url)
    )
    app = Flask(__name__, static_folder=None)

    @app.get("/health")
    def health() -> tuple[Response, int]:
        return jsonify(status="ok"), 200

    @app.get("/ready")
    def ready() -> tuple[Response, int]:
        if probe.is_ready():
            return jsonify(status="ready"), 200
        return jsonify(status="not_ready"), 503

    return app
