import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticRelevance:
    logits: tuple[float, ...]
    model_reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.logits, tuple) or any(
            type(value) not in (int, float) or not math.isfinite(value)
            for value in self.logits
        ):
            raise ValueError("Semantic scores must be finite numbers")
        if (
            not isinstance(self.model_reference, str)
            or not self.model_reference.strip()
            or len(self.model_reference) > 256
        ):
            raise ValueError("Invalid semantic model reference")
