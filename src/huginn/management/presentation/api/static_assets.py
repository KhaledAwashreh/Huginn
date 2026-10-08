"""Optional SPA delivery, web-ui-foundation design section 4."""

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from starlette.responses import FileResponse

_RESERVED_PATHS = {
    "api",
    "docs",
    "redoc",
    "openapi.json",
    "health",
    "ready",
    "assets",
}
_HASHED_ASSET = re.compile(r"-[A-Za-z0-9_-]{8,}\.[^.]+$")


def mount_frontend_assets(app: FastAPI, assets_path: Path | None) -> None:
    """Append bounded browser fallback after API routes; no build is required."""
    if assets_path is None:
        return
    root = assets_path.resolve()
    index = (root / "index.html").resolve()
    if not index.is_relative_to(root) or not index.is_file():
        return

    @app.get("/{frontend_path:path}", include_in_schema=False)
    def frontend(frontend_path: str) -> FileResponse:
        candidate = (root / frontend_path).resolve()
        if not candidate.is_relative_to(root):
            raise HTTPException(status_code=404)
        first_segment = frontend_path.split("/", 1)[0]
        # Existing API routes have already matched. Only build assets and browser
        # routes reach this fallback, never typoed operational/API endpoints.
        if first_segment in _RESERVED_PATHS and first_segment != "assets":
            raise HTTPException(status_code=404)
        if candidate.is_file():
            cache = (
                "public, max-age=31536000, immutable"
                if first_segment == "assets" and _HASHED_ASSET.search(candidate.name)
                else "no-store"
            )
            return FileResponse(candidate, headers={"Cache-Control": cache})
        if first_segment == "assets" or Path(frontend_path).suffix:
            raise HTTPException(status_code=404)
        return FileResponse(index, headers={"Cache-Control": "no-store"})
