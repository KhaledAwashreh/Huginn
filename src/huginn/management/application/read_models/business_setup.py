"""Profile configuration read model using existing owned aggregates."""

from dataclasses import dataclass

from huginn.management.domain.entities.business import Business
from huginn.management.domain.entities.ideal_client_profile import IdealClientProfile
from huginn.management.domain.entities.service_offering import ServiceOffering
from huginn.management.domain.entities.user import User


@dataclass(frozen=True)
class BusinessSetup:
    business: Business
    user: User
    service_offering: ServiceOffering | None
    ideal_client_profile: IdealClientProfile | None
