"""Shared response models."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class ResponseModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)


class PageResponse[T](ResponseModel):
    items: list[T]
    offset: int
    limit: int
    has_more: bool


NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


__all__ = ["NonBlank", "PageResponse", "ResponseModel"]
