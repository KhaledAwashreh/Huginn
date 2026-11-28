"""Single profile transaction over the existing business/configuration records."""

import logging
from collections.abc import Callable

from huginn.management.application.policies.icp_selection import validate_icp_selection
from huginn.management.application.read_models.business_setup import BusinessSetup
from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.domain.entities.business import Business
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.business_changes import BusinessChanges
from huginn.management.domain.value_objects.common import Page, Principal
from huginn.management.domain.value_objects.ideal_client_profile import (
    IdealClientProfileChanges,
    NewIdealClientProfile,
)
from huginn.management.domain.value_objects.service_offering import (
    NewServiceOffering,
    ServiceOfferingChanges,
)
from huginn.management.domain.value_objects.user import UserChanges
from huginn.management.persistence.contracts.repositories.business import (
    BusinessRepository,
)
from huginn.management.persistence.contracts.repositories.discovery_strategy import (
    ClientDiscoveryStrategyRepository,
)
from huginn.management.persistence.contracts.repositories.ideal_client_profile import (
    IdealClientProfileRepository,
)
from huginn.management.persistence.contracts.repositories.service_offering import (
    ServiceOfferingRepository,
)
from huginn.management.persistence.contracts.repositories.user import UserRepository
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol

logger = logging.getLogger(__name__)


class BusinessSetupService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        businesses_factory: Callable[[UnitOfWorkProtocol], BusinessRepository],
        users_factory: Callable[[UnitOfWorkProtocol], UserRepository],
        offerings_factory: Callable[[UnitOfWorkProtocol], ServiceOfferingRepository],
        profiles_factory: Callable[[UnitOfWorkProtocol], IdealClientProfileRepository],
        strategies_factory: Callable[
            [UnitOfWorkProtocol], ClientDiscoveryStrategyRepository
        ],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._businesses = businesses_factory
        self._users = users_factory
        self._offerings = offerings_factory
        self._profiles = profiles_factory
        self._strategies = strategies_factory

    @staticmethod
    def _single[T](page: Page[T]) -> T | None:
        if len(page.items) > 1 or page.has_more:
            raise ConflictError("The business has multiple saved configurations")
        return page.items[0] if page.items else None

    def _read(
        self, uow: UnitOfWorkProtocol, principal: Principal, business: Business
    ) -> BusinessSetup:
        user = self._users(uow).get_by_id(principal.user_id)
        if user is None:
            raise NotFoundError("User not found")
        strategies = self._strategies(uow)
        active = self._single(
            strategies.list_owned(business.id, limit=2, offset=0, active=True)
        )
        offerings, profiles = self._offerings(uow), self._profiles(uow)
        if active is not None:
            offering = offerings.get_owned(business.id, active.service_offering_id)
            profile = profiles.get_owned(business.id, active.ideal_client_profile_id)
            if offering is None or profile is None:
                raise NotFoundError("Discovery configuration not found")
        else:
            offering = self._single(
                offerings.list_owned(business.id, limit=2, offset=0)
            )
            profile = self._single(profiles.list_owned(business.id, limit=2, offset=0))
        return BusinessSetup(business, user, offering, profile)

    def get(self, principal: Principal) -> BusinessSetup:
        with self._uow_factory() as uow:
            businesses = self._businesses(uow)
            business_id = business_id_for_principal(principal, businesses)
            business = businesses.get_by_id_for_share(business_id)
            if business is None:
                raise NotFoundError("Business not found")
            return self._read(uow, principal, business)

    def save(
        self,
        principal: Principal,
        *,
        business_name: str,
        your_name: str,
        email: str | None = None,
        service_description: str,
        ideal_client_profile: IdealClientProfileChanges,
    ) -> BusinessSetup:
        values = {
            "name": ideal_client_profile.values["name"],
            **{
                field: ideal_client_profile.values.get(field, ())
                for field in (
                    "industries",
                    "company_sizes",
                    "geographies",
                    "exclusions",
                )
            },
        }
        validate_icp_selection(
            values["industries"], values["geographies"], values["exclusions"]
        )
        first_name, last_name = your_name.split(maxsplit=1)
        with self._uow_factory() as uow:
            businesses = self._businesses(uow)
            business_id = business_id_for_principal(principal, businesses)
            # Serialize the whole save, including first creation of offering/ICP.
            business = businesses.get_by_id_for_update(business_id)
            if business is None:
                raise NotFoundError("Business not found")
            current = self._read(uow, principal, business)
            if (
                email is not None
                and email.strip().lower() != current.user.email.strip().lower()
            ):
                raise ConflictError(
                    "Change your account email in Security and verify the new address."
                )
            if business.name != business_name:
                business = businesses.update(
                    business_id,
                    BusinessChanges({"name": business_name}, frozenset({"name"})),
                )
            name_values = {
                "first_name": first_name,
                "last_name": last_name,
            }
            # Leave the existing first/last boundary alone when the displayed name is unchanged.
            if your_name == f"{current.user.first_name} {current.user.last_name}":
                name_values.pop("first_name")
                name_values.pop("last_name")
            name_values = {
                key: value
                for key, value in name_values.items()
                if getattr(current.user, key) != value
            }
            user = (
                self._users(uow).update(
                    principal.user_id, UserChanges(name_values, frozenset(name_values))
                )
                if name_values
                else current.user
            )
            offerings, profiles = self._offerings(uow), self._profiles(uow)
            # A neutral hidden title makes ranking use the visible service description.
            if current.service_offering is None:
                offering = offerings.create(
                    NewServiceOffering(business_id, "Services", service_description)
                )
            else:
                offering_values = {
                    "name": "Services",
                    "description": service_description,
                }
                changed_offering = {
                    key: value
                    for key, value in offering_values.items()
                    if getattr(current.service_offering, key) != value
                }
                offering = (
                    offerings.update_owned(
                        business_id,
                        current.service_offering.id,
                        ServiceOfferingChanges(
                            changed_offering, frozenset(changed_offering)
                        ),
                    )
                    if changed_offering
                    else current.service_offering
                )
            if current.ideal_client_profile is None:
                profile = profiles.create(
                    NewIdealClientProfile(business_id=business_id, **values)
                )
            else:
                changed = {
                    key: value
                    for key, value in values.items()
                    if getattr(current.ideal_client_profile, key) != value
                }
                profile = (
                    profiles.update_owned(
                        business_id,
                        current.ideal_client_profile.id,
                        IdealClientProfileChanges(changed, frozenset(changed)),
                    )
                    if changed
                    else current.ideal_client_profile
                )
            if business is None or user is None or offering is None or profile is None:
                raise NotFoundError("Profile configuration not found")
            self._strategies(uow).set_single_configuration(
                business_id, offering.id, profile.id
            )
            uow.commit()
            logger.info("Business profile and discovery configuration saved")
            return BusinessSetup(business, user, offering, profile)
