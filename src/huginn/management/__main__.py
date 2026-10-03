"""Local management development entrypoint defined by ADR-0015."""

import logging

import uvicorn

from huginn.management.app import create_app

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the local ASGI development server defined by ADR-0015."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    app = create_app()
    logger.info("Starting management development server on 127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
