"""Strict shared validation primitives for management API boundaries."""

import re
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from huginn.management.presentation.api.constants.pagination import MAX_PAGE_LIMIT

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")


def _validate_email(value: str) -> str:
    if not _EMAIL_PATTERN.fullmatch(value):
        raise ValueError("invalid email address")
    return value.lower()


def _validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError("invalid IANA timezone") from exc
    return value


NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PageLimit = Annotated[int, Field(strict=True, ge=1, le=MAX_PAGE_LIMIT)]
PageOffset = Annotated[int, Field(strict=True, ge=0)]
UUIDValue = Annotated[UUID, Field(strict=True)]
Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=254),
    AfterValidator(_validate_email),
]
E164Phone = Annotated[str, StringConstraints(pattern=r"^\+[1-9][0-9]{1,14}$")]
IanaTimezone = Annotated[
    str, StringConstraints(min_length=1), AfterValidator(_validate_timezone)
]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class PatchModel(StrictModel):
    """Base for patches; track omitted fields separately from explicit nulls."""

    @property
    def supplied_fields(self) -> frozenset[str]:
        return frozenset(self.model_fields_set)
