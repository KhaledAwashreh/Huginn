"""Shared value shape used by Gold attribute models."""

from __future__ import annotations

type AttributeValue = tuple[str | None, ...] | str | None
