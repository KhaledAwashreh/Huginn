from dataclasses import dataclass

from huginn.management.domain.entities.prospect_origin import ProspectOrigin
from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True)
class OriginAppendResult:
    origin: ProspectOrigin
    created: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.origin, ProspectOrigin)
            or type(self.created) is not bool
        ):
            raise ValidationDomainError("Invalid origin append result")
