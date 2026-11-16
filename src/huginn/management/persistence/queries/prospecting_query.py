"""Business-scoped discovery, pursuit and suppression reads; ADR-0019."""

from datetime import datetime
from uuid import UUID

from huginn.management.application.protocols.business_company_state_query import (
    BusinessCompanyStateQuery,
)
from huginn.management.application.protocols.prospecting_query import ProspectingQuery
from huginn.management.application.read_models.current_company import CurrentCompany
from huginn.management.application.read_models.current_company_signal import (
    CurrentCompanySignal,
)
from huginn.management.application.read_models.current_source_context import (
    CurrentSourceContext,
)
from huginn.management.application.read_models.manageable_suppression_view import (
    ManageableSuppressionView,
)
from huginn.management.application.read_models.prospect_origin_view import (
    ProspectOriginView,
)
from huginn.management.application.read_models.prospect_view import ProspectView
from huginn.management.application.read_models.recommendation_view import (
    RecommendationView,
)
from huginn.management.application.requests.list_prospecting_request import (
    ListProspectingRequest,
)
from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.domain.value_objects.common import Page
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)
from huginn.management.persistence.row_models.current_company_signal import (
    CurrentCompanySignalRow,
)
from huginn.matchmaking.domain.value_objects.business_company_state import (
    BusinessCompanyState,
)

_COMPANY_COLUMNS = (
    "c.id,c.name,c.domain,c.business_sector,c.country,c.company_scale,c.company_status"
)
_SEARCH = "(strpos(lower(c.name),lower(%s))>0 OR strpos(lower(c.domain),lower(%s))>0)"


class PostgresProspectingQuery(ProspectingQuery):
    def __init__(
        self, work: ProspectingUnitOfWork, states: BusinessCompanyStateQuery
    ) -> None:
        if work.connection is None:
            raise RuntimeError("Prospecting query requires an active unit of work")
        self._work = work
        self._connection = work.connection
        self._states = states

    @staticmethod
    def _company(row) -> CurrentCompany:
        return CurrentCompany(
            row[0],
            row[1],
            row[2],
            None if row[3] is None else tuple(row[3]),
            row[4],
            row[5],
            row[6],
        )

    def _get_company(self, company_id: UUID) -> CurrentCompany:
        row = self._connection.execute(
            f"SELECT {_COMPANY_COLUMNS} FROM gold.company c WHERE c.id=%s",
            (company_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError("Company not found")
        return self._company(row)

    def _recommendation_view(
        self,
        business_id: UUID,
        recommendation: Recommendation,
        company: CurrentCompany,
        state: BusinessCompanyState,
        at: datetime,
        assessment_revision_id: UUID | None = None,
        presented_by_revision: dict[UUID, datetime] | None = None,
    ) -> RecommendationView:
        assessment = None
        revision_id = assessment_revision_id or recommendation.current_revision_id
        if revision_id is not None:
            assessment = self._work.assessment_revisions.get_owned(
                business_id, recommendation.id, revision_id
            )
        if assessment_revision_id is not None and assessment is None:
            raise NotFoundError("Recommendation assessment not found")
        current_ids = {
            row[0]
            for row in self._connection.execute(
                "SELECT observation_id FROM gold.current_source_evidence WHERE company_id=%s",
                (company.id,),
            ).fetchall()
        }
        if assessment is None:
            evidence_state = "not_assessed"
        elif not current_ids:
            evidence_state = "unavailable"
        elif (
            assessment.evidence_observation_ids
            and set(assessment.evidence_observation_ids) <= current_ids
        ):
            evidence_state = "current"
        else:
            evidence_state = "changed"
        return RecommendationView(
            recommendation,
            company,
            assessment,
            self._work.prospects.get_by_business_company(business_id, company.id),
            state,
            at,
            evidence_state,
            self._work.suppression_blocks.list_active(business_id, company.id, at),
            (presented_by_revision or {}).get(revision_id),
        )

    def _confirmed_presentations(
        self, business_id: UUID, recommendation_ids: tuple[UUID, ...]
    ) -> dict[UUID, datetime]:
        if not recommendation_ids:
            return {}
        rows = self._connection.execute(
            """SELECT selected_revision_id,min(presented_at)
            FROM operational.offer_cycles
            WHERE business_id=%s AND recommendation_id=ANY(%s)
              AND status='confirmed' AND presented_at IS NOT NULL
            GROUP BY selected_revision_id""",
            (business_id, list(recommendation_ids)),
        ).fetchall()
        return dict(rows)

    def list_recommendations(
        self,
        business_id: UUID,
        request: ListProspectingRequest,
        status: RecommendationStatus | None,
        at: datetime,
    ) -> Page[RecommendationView]:
        where = [
            "r.business_id=%s",
            "(r.status<>'open' OR (NOT EXISTS(SELECT 1 FROM operational.prospects p WHERE p.business_id=r.business_id AND p.company_id=r.company_id) AND NOT EXISTS(SELECT 1 FROM operational.suppression_blocks b WHERE b.business_id=r.business_id AND b.company_id=r.company_id AND b.kind='pause' AND b.cleared_at IS NULL AND b.effective_at<=%s AND (b.expires_at IS NULL OR b.expires_at>%s))))",
        ]
        parameters: list[object] = [business_id, at, at]
        if status is not None:
            where.append("r.status=%s")
            parameters.append(status.value)
        if request.search:
            where.append(_SEARCH)
            parameters.extend((request.search, request.search))
        parameters.extend((request.limit + 1, request.offset))
        rows = self._connection.execute(
            f"""SELECT r.id,{_COMPANY_COLUMNS}
            FROM operational.recommendations r
            JOIN gold.company c ON c.id=r.company_id
            LEFT JOIN operational.assessment_revisions v ON v.id=r.current_revision_id AND v.recommendation_id=r.id AND v.business_id=r.business_id
            LEFT JOIN LATERAL (
                SELECT CASE WHEN jsonb_typeof(a->'assessment_snapshot'->'score')='number'
                            THEN (a->'assessment_snapshot'->>'score')::numeric END AS score
                FROM jsonb_array_elements(v.strategy_assessments) a
                ORDER BY score DESC NULLS LAST LIMIT 1
            ) ranking ON true
            WHERE {" AND ".join(where)}
            ORDER BY ranking.score DESC NULLS LAST,v.assessed_at DESC NULLS LAST,r.created_at DESC,r.id
            LIMIT %s OFFSET %s""",
            tuple(parameters),
        ).fetchall()
        selected = rows[: request.limit]
        states = (
            self._states.company_states(
                business_id, tuple(row[1] for row in selected), at
            )
            if selected
            else ()
        )
        presented_by_revision = self._confirmed_presentations(
            business_id, tuple(row[0] for row in selected)
        )
        views = []
        for row, state in zip(selected, states, strict=True):
            recommendation = self._work.recommendations.get_owned(business_id, row[0])
            if recommendation is None:
                raise NotFoundError("Recommendation not found")
            views.append(
                self._recommendation_view(
                    business_id,
                    recommendation,
                    self._company(row[1:]),
                    state,
                    at,
                    presented_by_revision=presented_by_revision,
                )
            )
        return Page(
            tuple(views), request.offset, request.limit, len(rows) > request.limit
        )

    def get_recommendation(
        self,
        business_id: UUID,
        recommendation_id: UUID,
        at: datetime,
        assessment_revision_id: UUID | None = None,
    ) -> RecommendationView | None:
        recommendation = self._work.recommendations.get_owned(
            business_id, recommendation_id
        )
        if recommendation is None:
            return None
        company = self._get_company(recommendation.company_id)
        state = self._states.company_states(business_id, (company.id,), at)[0]
        return self._recommendation_view(
            business_id,
            recommendation,
            company,
            state,
            at,
            assessment_revision_id,
            self._confirmed_presentations(business_id, (recommendation.id,)),
        )

    def _origins_by_prospect(
        self, business_id: UUID, prospect_ids: tuple[UUID, ...]
    ) -> dict[UUID, tuple[ProspectOriginView, ...]]:
        origins = self._work.origins.list_for_prospects(business_id, prospect_ids)
        recommendations = {
            value.id: value
            for value in self._work.recommendations.get_many_owned(
                business_id, tuple({origin.recommendation_id for origin in origins})
            )
        }
        assessments = {
            (value.recommendation_id, value.id): value
            for value in self._work.assessment_revisions.get_many_owned(
                business_id,
                tuple({origin.assessment_revision_id for origin in origins}),
            )
        }
        grouped: dict[UUID, list[ProspectOriginView]] = {
            prospect_id: [] for prospect_id in prospect_ids
        }
        for origin in origins:
            recommendation = recommendations.get(origin.recommendation_id)
            assessment = assessments.get(
                (origin.recommendation_id, origin.assessment_revision_id)
            )
            if recommendation is None or assessment is None:
                raise NotFoundError("Saved assessment not found")
            grouped[origin.prospect_id].append(
                ProspectOriginView(origin, recommendation, assessment)
            )
        return {key: tuple(values) for key, values in grouped.items()}

    def list_prospects(
        self,
        business_id: UUID,
        request: ListProspectingRequest,
        stage: ProspectStage | None,
        at: datetime,
    ) -> Page[ProspectView]:
        where = ["p.business_id=%s"]
        parameters: list[object] = [business_id]
        if stage is not None:
            where.append("p.stage=%s")
            parameters.append(stage.value)
        if request.search:
            where.append(_SEARCH)
            parameters.extend((request.search, request.search))
        parameters.extend((request.limit + 1, request.offset))
        rows = self._connection.execute(
            f"SELECT p.id,{_COMPANY_COLUMNS} FROM operational.prospects p JOIN gold.company c ON c.id=p.company_id WHERE {' AND '.join(where)} ORDER BY p.updated_at DESC,p.id LIMIT %s OFFSET %s",
            tuple(parameters),
        ).fetchall()
        selected = rows[: request.limit]
        prospect_ids = tuple(row[0] for row in selected)
        prospects = {
            value.id: value
            for value in self._work.prospects.get_many_owned(business_id, prospect_ids)
        }
        origins = self._origins_by_prospect(business_id, prospect_ids)
        views = []
        for row in selected:
            prospect = prospects.get(row[0])
            if prospect is None:
                raise NotFoundError("Prospect not found")
            views.append(
                ProspectView(
                    prospect, self._company(row[1:]), origins[prospect.id], None
                )
            )
        return Page(
            tuple(views), request.offset, request.limit, len(rows) > request.limit
        )

    def _current_source_context(
        self, company_id: UUID, origins: tuple[ProspectOriginView, ...], at: datetime
    ) -> CurrentSourceContext:
        retained_ids = {
            observation_id
            for origin in origins
            for observation_id in origin.assessment.evidence_observation_ids
        }
        rows = self._connection.execute(
            """WITH current_sources AS (
                 SELECT DISTINCT ON (observation_id)
                   id,signal_type,source,source_url,description,stage,
                   occurred_at,ingested_at,observation_id,observed_at,
                   evidence_kind,hiring_state
                 FROM gold.current_source_evidence WHERE company_id=%s
                   AND observed_at<=%s AND (occurred_at IS NULL OR occurred_at<=%s)
                 ORDER BY observation_id,id DESC
               )
               SELECT *,count(*) FILTER (WHERE observation_id=ANY(%s)) OVER (),
                      count(*) OVER ()
               FROM current_sources
               ORDER BY occurred_at DESC NULLS LAST,id DESC LIMIT 51""",
            (company_id, at, at, list(retained_ids)),
        ).fetchall()
        signals = tuple(
            CurrentCompanySignal(
                **CurrentCompanySignalRow(
                    id=row[0],
                    signal_type=row[1],
                    source=row[2],
                    source_url=row[3],
                    description=row[4],
                    stage=row[5],
                    occurred_at=row[6],
                    ingested_at=row[7],
                    observation_id=row[8],
                    observed_at=row[9],
                    evidence_kind=row[10],
                    hiring_state=row[11],
                ).model_dump()
            )
            for row in rows[:50]
        )
        if not rows:
            state = "unavailable"
        elif not retained_ids:
            state = "not_assessed"
        elif rows[0][12] == rows[0][13] == len(retained_ids):
            state = "current"
        else:
            state = "changed"
        return CurrentSourceContext(signals, len(rows) > 50, state)

    def get_prospect(
        self, business_id: UUID, prospect_id: UUID, at: datetime
    ) -> ProspectView | None:
        prospect = self._work.prospects.get_owned(business_id, prospect_id)
        if prospect is None:
            return None
        origins = self._origins_by_prospect(business_id, (prospect.id,))
        return ProspectView(
            prospect,
            self._get_company(prospect.company_id),
            origins[prospect.id],
            self._work.activities.list_owned(business_id, prospect.id),
            self._current_source_context(prospect.company_id, origins[prospect.id], at),
        )

    def list_manageable_suppressions(
        self, business_id: UUID, request: ListProspectingRequest, at: datetime
    ) -> Page[ManageableSuppressionView]:
        where = [
            "EXISTS (SELECT 1 FROM operational.suppression_blocks b WHERE b.business_id=%s AND b.company_id=c.id AND b.kind IN ('pause','rejection') AND b.cleared_at IS NULL AND b.effective_at<=%s AND (b.expires_at IS NULL OR b.expires_at>%s))"
        ]
        parameters: list[object] = [business_id, at, at]
        if request.search:
            where.append(_SEARCH)
            parameters.extend((request.search, request.search))
        parameters.extend((request.limit + 1, request.offset))
        rows = self._connection.execute(
            f"SELECT {_COMPANY_COLUMNS} FROM gold.company c WHERE {' AND '.join(where)} ORDER BY lower(c.name),c.id LIMIT %s OFFSET %s",
            tuple(parameters),
        ).fetchall()
        selected = rows[: request.limit]
        states = (
            self._states.company_states(
                business_id, tuple(row[0] for row in selected), at
            )
            if selected
            else ()
        )
        views = []
        for row, state in zip(selected, states, strict=True):
            company = self._company(row)
            blocks = self._work.suppression_blocks.list_active(
                business_id, company.id, at
            )
            prospect = self._work.prospects.get_by_business_company(
                business_id, company.id
            )
            views.append(
                ManageableSuppressionView(company, blocks, prospect, state, at)
            )
        return Page(
            tuple(views), request.offset, request.limit, len(rows) > request.limit
        )
