"""Explicit editable Business fields without personal-profile copying."""

from collections.abc import Mapping
from dataclasses import dataclass

from huginn.management.domain.value_objects.common import JsonObject


@dataclass(frozen=True)
class BusinessChanges:
    values: Mapping[str, str | None | tuple[JsonObject, ...]]
    supplied_fields: frozenset[str]
