"""Pure, read-only policy for assessing source-backed company attributes."""

from huginn.elt.gold.attribute_promotion.models import (
    CompanyAttributes,
    FieldProposal,
    SourceFact,
)
from huginn.elt.gold.attribute_promotion.policy import MAPPING_VERSION, assess

__all__ = [
    "CompanyAttributes",
    "FieldProposal",
    "MAPPING_VERSION",
    "SourceFact",
    "assess",
]
