"""Pagination behavior shared by management list services."""

POSTGRES_BIGINT_MAX = 2**63 - 1


def empty_page(offset: int, limit: int) -> dict[str, object] | None:
    """Return an empty response page when PostgreSQL cannot represent offset."""
    if offset <= POSTGRES_BIGINT_MAX:
        return None
    return {"items": [], "offset": offset, "limit": limit, "has_more": False}
