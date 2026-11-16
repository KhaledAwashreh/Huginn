from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class CompanyFitAssessment:
    dimensions: Mapping[str, str]
    explicitly_excluded: bool = False

    def __post_init__(self) -> None:
        if any(
            value not in {"match", "unknown", "mismatch"}
            for value in self.dimensions.values()
        ):
            raise ValueError("invalid company fit status")
        object.__setattr__(self, "dimensions", MappingProxyType(dict(self.dimensions)))
        if type(self.explicitly_excluded) is not bool:
            raise ValueError("explicit exclusion must be boolean")

    @property
    def eligible(self) -> bool:
        return (
            not self.explicitly_excluded and "mismatch" not in self.dimensions.values()
        )

    @property
    def industry(self) -> str:
        return self.dimensions.get("industry", "unknown")

    @property
    def size(self) -> str:
        return self.dimensions.get("size", "unknown")

    @property
    def country(self) -> str:
        return self.dimensions.get("country", "unknown")
