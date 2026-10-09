from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    kind: str
    unit: str
    value: int | float | None

    def __post_init__(self) -> None:
        if not self.kind or not self.unit:
            raise ValueError("metric kind and unit are required")
        if self.value is not None and isinstance(self.value, bool):
            raise ValueError("metric value must be numeric")
