"""Process health and read-only database readiness endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from huginn.management.dependencies.services import get_readiness
from huginn.management.openapi_responses import error_responses

router = APIRouter(tags=["health"])


@router.get("/health", responses=error_responses())
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/ready",
    responses={
        **error_responses(),
        503: {
            "description": "Management service is not ready",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["status"],
                        "properties": {"status": {"const": "not_ready"}},
                    }
                }
            },
        },
    },
)
def ready(
    readiness: Annotated[Any, Depends(get_readiness)], response: Response
) -> dict[str, str]:
    if readiness.is_ready():
        return {"status": "ready"}
    response.status_code = 503
    return {"status": "not_ready"}
