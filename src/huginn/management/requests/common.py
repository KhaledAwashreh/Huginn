"""Strict primitives shared by request models."""

from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
)


class RequestModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class PatchRequest(RequestModel):
    @property
    def supplied_fields(self) -> frozenset[str]:
        return frozenset(self.model_fields_set)


NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _parse_uuid_string(value: object) -> object:
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return value
    return value


RequestUUID = Annotated[UUID, BeforeValidator(_parse_uuid_string), Field(strict=True)]
