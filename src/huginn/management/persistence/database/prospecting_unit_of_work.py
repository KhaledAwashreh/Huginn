"""Shared Business/Company transaction boundary; ADR-0019."""

import sys
from typing import Self
from uuid import UUID

from huginn.management.persistence.contracts.database import ConnectionFactory
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)
from huginn.management.persistence.database.unit_of_work import UnitOfWork
from huginn.management.persistence.repositories.assessment_revision import (
    PostgresAssessmentRevisionRepository,
)
from huginn.management.persistence.repositories.business import (
    PostgresBusinessRepository,
)
from huginn.management.persistence.repositories.business_recommendation_preferences import (
    PostgresBusinessRecommendationPreferencesRepository,
)
from huginn.management.persistence.repositories.command_receipt import (
    PostgresCommandReceiptRepository,
)
from huginn.management.persistence.repositories.offer_cycle import (
    PostgresOfferCycleRepository,
)
from huginn.management.persistence.repositories.prospect import (
    PostgresProspectRepository,
)
from huginn.management.persistence.repositories.prospect_activity import (
    PostgresProspectActivityRepository,
)
from huginn.management.persistence.repositories.prospect_origin import (
    PostgresProspectOriginRepository,
)
from huginn.management.persistence.repositories.recommendation import (
    PostgresRecommendationRepository,
)
from huginn.management.persistence.repositories.recommendation_assessment_feedback import (
    PostgresRecommendationAssessmentFeedbackRepository,
)
from huginn.management.persistence.repositories.suppression_block import (
    PostgresSuppressionBlockRepository,
)


class PostgresProspectingUnitOfWork(UnitOfWork, ProspectingUnitOfWork):
    def __init__(
        self, connection_factory: ConnectionFactory, *, read_only: bool = False
    ) -> None:
        super().__init__(connection_factory)
        self._read_only = read_only

    def __enter__(self) -> Self:
        if self.connection is not None:
            raise RuntimeError("unit of work is already active")
        super().__enter__()
        try:
            connection = self._require_connection()
            if self._read_only:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY", ()
                    )
            self.businesses = PostgresBusinessRepository(connection)
            self.business_recommendation_preferences = (
                PostgresBusinessRecommendationPreferencesRepository(connection)
            )
            self.recommendations = PostgresRecommendationRepository(connection)
            self.assessment_revisions = PostgresAssessmentRevisionRepository(connection)
            self.prospects = PostgresProspectRepository(connection)
            self.origins = PostgresProspectOriginRepository(connection)
            self.activities = PostgresProspectActivityRepository(connection)
            self.commands = PostgresCommandReceiptRepository(connection)
            self.offer_cycles = PostgresOfferCycleRepository(connection)
            self.suppression_blocks = PostgresSuppressionBlockRepository(connection)
            self.recommendation_feedback = (
                PostgresRecommendationAssessmentFeedbackRepository(connection)
            )
        except BaseException:
            super().__exit__(*sys.exc_info())
            raise
        return self

    def lock_business_company(self, business_id: UUID, company_id: UUID) -> None:
        connection = self._require_connection()
        if self._finished:
            raise RuntimeError("unit of work is already finished")
        if self._read_only:
            raise RuntimeError(
                "read-only unit of work cannot acquire offer or command locks"
            )
        key = f"huginn:prospecting:{business_id}:{company_id}"
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,)
            )
