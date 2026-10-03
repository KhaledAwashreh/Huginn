"""Conversions at the HTTP, domain, and response boundaries."""

import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


def _plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return {key: _plain(item) for key, item in value.model_dump().items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _plain(getattr(value, field.name)) for field in fields(value)
        }
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, Enum):
        return _plain(value.value)
    return value


def _domain_value(value: Any, *, in_json_collection: bool = False) -> Any:
    """Convert request collections to the immutable tuple form used by domain."""
    if isinstance(value, BaseModel):
        return {
            key: _domain_value(item, in_json_collection=in_json_collection)
            for key, item in value.model_dump().items()
        }
    if isinstance(value, UUID) and in_json_collection:
        return str(value)
    if isinstance(value, list):
        return tuple(_domain_value(item, in_json_collection=True) for item in value)
    if isinstance(value, dict):
        return {
            key: _domain_value(item, in_json_collection=True)
            for key, item in value.items()
        }
    if isinstance(value, Enum):
        return _domain_value(value.value)
    return value


def request_to_domain[RequestT: BaseModel, DomainT](
    model: RequestT, domain_type: type[DomainT], **injected: Any
) -> DomainT:
    """Build a domain command using validated fields and server-side values."""
    values = model.model_dump()
    if hasattr(model, "supplied_fields"):
        values = model.model_dump(exclude_unset=True)
    values = {key: _domain_value(value) for key, value in values.items()}
    values.update(injected)
    if not is_dataclass(domain_type):
        raise TypeError("domain_type must be a dataclass")
    accepted = {field.name for field in fields(domain_type)}
    return domain_type(
        **{key: value for key, value in values.items() if key in accepted}
    )


def request_to_changes[RequestT: BaseModel, ChangesT](
    model: RequestT, changes_type: type[ChangesT]
) -> ChangesT:
    """Map a patch to the domain's values plus explicit supplied-field set."""
    supplied = getattr(model, "supplied_fields", frozenset(model.model_fields_set))
    values = {
        key: _domain_value(value)
        for key, value in model.model_dump(exclude_unset=True).items()
    }
    return changes_type(values=values, supplied_fields=frozenset(supplied))


def response_from_domain[ResponseT: BaseModel](
    value: Any, response_type: type[ResponseT]
) -> ResponseT:
    """Validate and filter a domain result through its declared response model."""
    if is_dataclass(value) and not isinstance(value, type):
        source = {field.name: getattr(value, field.name) for field in fields(value)}
    elif isinstance(value, dict):
        source = value
    else:
        raise TypeError("response value must be a domain dataclass or mapping")
    # JSON mode intentionally accepts JSON UUID strings while retaining strict
    # validation for Python-mode booleans, numbers, and other primitive fields.
    return response_type.model_validate_json(
        json.dumps(_plain(source), default=_json_default)
    )


def _json_default(value: Any) -> str:
    if isinstance(value, (UUID, date, datetime)):
        return value.isoformat() if not isinstance(value, UUID) else str(value)
    raise TypeError(f"Unsupported boundary value: {type(value).__name__}")
