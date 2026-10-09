"""Strict filter vocabulary for Matches reads."""

from typing import Literal

MatchStatusFilter = Literal["new", "contacted", "responded", "dismissed", "converted"]
