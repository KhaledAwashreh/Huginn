"""Operator rollback gate for starting new discovery work."""

from fastapi import HTTPException

from huginn.management.presentation.api.dependencies.services import Management


def require_new_discovery_work(dependencies: Management) -> None:
    if not dependencies.discovery_new_work_enabled:
        raise HTTPException(status_code=503)
