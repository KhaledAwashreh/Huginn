"""Local management development entrypoint defined by ADR-0011."""

import logging

from huginn.management.app import create_app

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the local development server defined by ADR-0011."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    app = create_app()
    logger.info("Starting management development server on 127.0.0.1:8000")
    app.run(host="127.0.0.1", port=8000, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
