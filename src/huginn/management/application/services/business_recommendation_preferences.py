"""Authenticated Business recommendation preference operations."""

from collections.abc import Callable

from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.domain.entities.business_recommendation_preferences import (
    BusinessRecommendationPreferences,
)
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.domain.value_objects.business_recommendation_preferences import (
    BusinessRecommendationPreferencesChanges,
)
from huginn.management.domain.value_objects.common import Principal
from huginn.management.persistence.contracts.repositories.business import (
    BusinessRepository,
)
from huginn.management.persistence.contracts.repositories.business_recommendation_preferences import (
    BusinessRecommendationPreferencesRepository,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class BusinessRecommendationPreferencesService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        businesses_factory: Callable[[UnitOfWorkProtocol], BusinessRepository],
        preferences_factory: Callable[
            [UnitOfWorkProtocol], BusinessRecommendationPreferencesRepository
        ],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._businesses_factory = businesses_factory
        self._preferences_factory = preferences_factory

    def get(self, principal: Principal) -> BusinessRecommendationPreferences:
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(
                principal, self._businesses_factory(uow)
            )
            preferences = self._preferences_factory(uow).get(business_id)
            if preferences is None:
                raise NotFoundError("Business recommendation preferences not found")
            return preferences

    def update(
        self,
        principal: Principal,
        changes: BusinessRecommendationPreferencesChanges,
    ) -> BusinessRecommendationPreferences:
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(
                principal, self._businesses_factory(uow)
            )
            preferences = self._preferences_factory(uow).update(business_id, changes)
            if preferences is None:
                raise NotFoundError("Business recommendation preferences not found")
            uow.commit()
            return preferences
