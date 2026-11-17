"""Business-owned recommendation input queries; architecture section 9."""

import json
import re
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from huginn.management.application.protocols.recommendation_generation import (
    RecommendationGenerationSource,
)
from huginn.management.application.read_models.recommendation_company import (
    RecommendationCompany,
)
from huginn.management.application.read_models.recommendation_profile import (
    RecommendationProfile,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.matchmaking.domain.value_objects.business_company_state import (
    BusinessCompanyState,
)
from huginn.matchmaking.domain.value_objects.ranking_observation import (
    RankingObservation,
)


class PostgresRecommendationGenerationSource(RecommendationGenerationSource):
    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    def lock_configuration(self, business_id: UUID) -> None:
        self.connection.execute(
            "SELECT id FROM operational.businesses WHERE id=%s FOR SHARE",
            (business_id,),
        ).fetchone()

    def lock_successful_run_window(self, business_id: UUID) -> None:
        self.connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"recommendation-generation/{business_id}",),
        ).fetchone()

    def successful_on_demand_runs_since(
        self, business_id: UUID, since: datetime
    ) -> tuple[datetime, ...]:
        rows = self.connection.execute(
            "SELECT recorded_at FROM operational.command_receipts "
            "WHERE business_id=%s AND scope='recommendation_generation:on_demand' "
            "AND recorded_at>%s ORDER BY recorded_at",
            (business_id, since),
        ).fetchall()
        return tuple(row[0] for row in rows)

    def active_strategy_ids(self, owner_user_id: UUID) -> tuple[UUID, ...]:
        return tuple(
            row[0]
            for row in self.connection.execute(
                """SELECT s.id FROM operational.client_discovery_strategies s
                JOIN operational.service_offerings o
                    ON o.id=s.service_offering_id AND o.business_id=s.business_id
                JOIN operational.ideal_client_profiles i
                    ON i.id=s.ideal_client_profile_id AND i.business_id=s.business_id
                JOIN operational.businesses b ON b.id=s.business_id
                JOIN operational.users u ON u.id=b.owner_user_id
                JOIN operational.accounts a ON a.id=u.account_id
                WHERE b.owner_user_id=%s AND s.is_active AND a.status='active'
                ORDER BY s.id""",
                (owner_user_id,),
            ).fetchall()
        )

    def active_profiles(self, owner_user_id: UUID) -> tuple[RecommendationProfile, ...]:
        profiles = []
        for strategy_id in self.active_strategy_ids(owner_user_id):
            profile = self.profile(owner_user_id, strategy_id)
            if profile is not None:
                profiles.append(profile)
        return tuple(profiles)

    def profile(
        self, owner_user_id: UUID, strategy_id: UUID
    ) -> RecommendationProfile | None:
        row = self.connection.execute(
            """SELECT s.id, jsonb_build_object(
                'strategy', to_jsonb(s), 'offering', to_jsonb(o),
                'icp', to_jsonb(i), 'professional_profile', to_jsonb(p)),
                o.name || E'\\n' || o.description
            FROM operational.client_discovery_strategies s
            JOIN operational.service_offerings o
                ON o.id=s.service_offering_id AND o.business_id=s.business_id
            JOIN operational.ideal_client_profiles i
                ON i.id=s.ideal_client_profile_id AND i.business_id=s.business_id
            JOIN operational.businesses b ON b.id=s.business_id
            LEFT JOIN operational.professional_profiles p ON p.user_id=b.owner_user_id
            WHERE b.owner_user_id=%s AND s.id=%s AND s.is_active""",
            (owner_user_id, strategy_id),
        ).fetchone()
        return (
            RecommendationProfile(row[0], _json_dumps(row[1]), row[2]) if row else None
        )

    def candidates(
        self,
        terms: tuple[str, ...],
        cutoff: datetime,
        as_of: datetime,
        limit: int = 200,
        *,
        exclude_company_ids: frozenset[UUID] = frozenset(),
        offset: int = 0,
    ) -> tuple[RecommendationCompany, ...]:
        if cutoff.tzinfo is None or as_of.tzinfo is None or cutoff > as_of:
            raise ValueError("invalid recommendation evidence window")
        if not 1 <= limit <= 200:
            raise ValueError("candidate limit must be between 1 and 200")
        if type(offset) is not int or offset < 0:
            raise ValueError("candidate offset must be non-negative")
        terms = tuple(sorted({term.lower() for term in terms if term.strip()}))
        if not terms:
            return ()
        self.connection.execute(
            "SELECT set_config('statement_timeout','15000',true)"
        ).fetchone()
        patterns = [r"\m" + re.escape(term) + r"\M" for term in terms]
        rows = self.connection.execute(
            """WITH eligible AS MATERIALIZED (
                SELECT company_id, observation_id, description, occurred_at, observed_at,
                    source, source_url, source_country
                FROM gold.current_source_evidence
                WHERE (occurred_at IS NULL OR occurred_at BETWEEN %s AND %s)
                  AND (observed_at IS NULL OR observed_at <= %s)
                  AND NOT (company_id = ANY(%s::uuid[]))
            ), selected AS (
                SELECT e.company_id, count(DISTINCT term) AS hits
                FROM eligible e CROSS JOIN unnest(%s::text[]) AS term
                WHERE e.description ~* term
                GROUP BY e.company_id
                ORDER BY hits DESC,e.company_id LIMIT %s OFFSET %s
            )
            SELECT c.id,c.name,c.domain,c.business_sector,c.country,c.company_scale,
                e.observation_id,e.description,e.occurred_at,e.observed_at,e.source,
                e.source_url,e.source_country
            FROM selected s JOIN gold.company c ON c.id=s.company_id
            JOIN eligible e ON e.company_id=c.id
            ORDER BY s.hits DESC,c.id,e.occurred_at NULLS LAST,e.observation_id""",
            (
                cutoff,
                as_of,
                as_of,
                sorted(exclude_company_ids),
                patterns,
                limit,
                offset,
            ),
        ).fetchall()
        grouped: dict[UUID, list] = {}
        metadata: dict[UUID, tuple] = {}
        countries: dict[UUID, list] = {}
        for row in rows:
            metadata[row[0]] = row[:6]
            grouped.setdefault(row[0], []).append(RankingObservation(*row[6:12]))
            if row[12]:
                countries.setdefault(row[0], []).append((row[6], row[12]))
        return tuple(
            RecommendationCompany(
                *metadata[key][:3],
                tuple(metadata[key][3]) if metadata[key][3] is not None else None,
                *metadata[key][4:],
                tuple(observations),
                tuple(countries.get(key, ())),
            )
            for key, observations in grouped.items()
        )

    def candidate_is_current(
        self, company: RecommendationCompany, cutoff: datetime, as_of: datetime
    ) -> bool:
        if cutoff.tzinfo is None or as_of.tzinfo is None or cutoff > as_of:
            raise ValueError("invalid recommendation evidence window")
        row = self.connection.execute(
            """SELECT id,name,domain,business_sector,country,company_scale
            FROM gold.company WHERE id=%s""",
            (company.company_id,),
        ).fetchone()
        if row is None:
            return False
        expected_country = (
            company.source_country_value
            if company.country_evidence_id is not None
            else company.country
        )
        if (
            row[0] != company.company_id
            or row[1] != company.name
            or row[2] != company.domain
            or (None if row[3] is None else tuple(row[3])) != company.business_sector
            or row[4] != expected_country
            or row[5] != company.company_scale
        ):
            return False
        observations = company.observations
        if not observations:
            return False
        observation_ids = [item.observation_id for item in observations]
        evidence_rows = self.connection.execute(
            """SELECT observation_id,description,occurred_at,observed_at,
                source,source_url,source_country
            FROM gold.current_source_evidence
            WHERE company_id=%s AND observation_id=ANY(%s::uuid[])
              AND (occurred_at IS NULL OR occurred_at BETWEEN %s AND %s)
              AND (observed_at IS NULL OR observed_at<=%s)
            ORDER BY observation_id""",
            (company.company_id, observation_ids, cutoff, as_of, as_of),
        ).fetchall()
        if len(evidence_rows) != len(observations):
            return False
        actual = {value[0]: value[1:] for value in evidence_rows}
        expected = {
            item.observation_id: (
                item.description,
                item.occurred_at,
                item.observed_at,
                item.source,
                item.source_url,
                dict(company.source_countries).get(item.observation_id),
            )
            for item in observations
        }
        return actual == expected

    def current_company_for_revision(
        self, revision: AssessmentRevision, as_of: datetime
    ) -> RecommendationCompany | None:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("recommendation evidence check needs an aware time")
        cutoff = as_of - timedelta(days=365)
        strategy_assessments = revision.strategy_assessments
        facts = [
            item.assessment_snapshot.to_json_object().get("company_facts")
            for item in strategy_assessments
        ]
        if not facts or facts[0] is None or any(value != facts[0] for value in facts):
            return None
        frozen = facts[0]
        try:
            observation_ids = tuple(revision.evidence_observation_ids)
            frozen_ids = tuple(
                UUID(value.to_json_object()["observation_id"])
                for value in revision.evidence_snapshots
            )
            if set(observation_ids) != set(frozen_ids) or len(frozen_ids) != len(
                observation_ids
            ):
                return None
            observation_by_id = {
                UUID(value["observation_id"]): value
                for value in (
                    item.to_json_object() for item in revision.evidence_snapshots
                )
            }
        except KeyError, TypeError, ValueError:
            return None
        company_row = self.connection.execute(
            """SELECT id,name,domain,business_sector,country,company_scale
            FROM gold.company WHERE id=%s""",
            (revision.company_id,),
        ).fetchone()
        if company_row is None:
            return None
        sector = None if company_row[3] is None else list(company_row[3])
        if (
            str(frozen.get("company_id")) != str(company_row[0])
            or frozen.get("name") != company_row[1]
            or frozen.get("domain") != company_row[2]
            or frozen.get("business_sector") != sector
            or frozen.get("raw_country") != company_row[4]
            or frozen.get("company_scale") != company_row[5]
        ):
            return None
        rows = self.connection.execute(
            """SELECT observation_id,description,occurred_at,observed_at,
                source,source_url,source_country
            FROM gold.current_source_evidence
            WHERE company_id=%s AND observation_id=ANY(%s::uuid[])
              AND (occurred_at IS NULL OR occurred_at BETWEEN %s AND %s)
              AND (observed_at IS NULL OR observed_at<=%s)
            ORDER BY observation_id""",
            (
                revision.company_id,
                list(observation_ids),
                cutoff,
                as_of,
                as_of,
            ),
        ).fetchall()
        if len(rows) != len(observation_ids):
            return None
        observations = []
        countries = []
        for row in rows:
            snapshot = observation_by_id[row[0]]
            if (
                snapshot.get("description") != row[1]
                or snapshot.get("occurred_at") != _iso(row[2])
                or snapshot.get("observed_at") != _iso(row[3])
                or snapshot.get("source") != row[4]
                or snapshot.get("source_url") != row[5]
                or snapshot.get("source_country") != row[6]
            ):
                return None
            observations.append(RankingObservation(*row[:6]))
            if row[6]:
                countries.append((row[0], row[6]))
        return RecommendationCompany(
            company_row[0],
            company_row[1],
            company_row[2],
            None if company_row[3] is None else tuple(company_row[3]),
            company_row[4],
            company_row[5],
            tuple(observations),
            tuple(countries),
        )

    def company_states(
        self,
        business_id: UUID,
        company_ids: tuple[UUID, ...],
        as_of: datetime,
        *,
        exclude_offer_cycle_id: UUID | None = None,
    ) -> tuple[BusinessCompanyState, ...]:
        if not company_ids:
            return ()
        rows = self.connection.execute(
            """WITH scope AS (
                SELECT %s::uuid AS business_id, %s::timestamptz AS as_of,
                    %s::uuid AS excluded_preparing_cycle
            ), requested AS (
                SELECT company_id, ordinal FROM unnest(%s::uuid[])
                    WITH ORDINALITY AS item(company_id,ordinal)
            )
            SELECT requested.company_id,
                recommendation.first_presented_at,
                (SELECT max(block.expires_at) FROM operational.suppression_blocks block
                    WHERE block.business_id=scope.business_id AND block.company_id=requested.company_id
                      AND block.kind='cooldown' AND block.effective_at<=scope.as_of
                      AND block.cleared_at IS NULL AND block.expires_at>scope.as_of),
                (SELECT max(block.expires_at) FROM operational.suppression_blocks block
                    WHERE block.business_id=scope.business_id AND block.company_id=requested.company_id
                      AND block.kind='pause' AND block.effective_at<=scope.as_of
                      AND block.cleared_at IS NULL AND block.expires_at>scope.as_of),
                EXISTS (SELECT 1 FROM operational.suppression_blocks block
                    WHERE block.business_id=scope.business_id AND block.company_id=requested.company_id
                      AND block.kind='pause' AND block.expires_at IS NULL
                      AND block.effective_at<=scope.as_of AND block.cleared_at IS NULL),
                EXISTS (SELECT 1 FROM operational.suppression_blocks block
                    WHERE block.business_id=scope.business_id AND block.company_id=requested.company_id
                      AND block.kind='rejection' AND block.effective_at<=scope.as_of
                      AND block.cleared_at IS NULL),
                EXISTS (SELECT 1 FROM operational.prospects prospect
                    WHERE prospect.business_id=scope.business_id AND prospect.company_id=requested.company_id),
                EXISTS (SELECT 1 FROM operational.offer_cycles cycle
                    WHERE cycle.business_id=scope.business_id AND cycle.company_id=requested.company_id
                      AND cycle.status IN ('preparing','sending')
                      AND (cycle.status='sending' OR scope.excluded_preparing_cycle IS NULL
                           OR cycle.id<>scope.excluded_preparing_cycle)),
                EXISTS (SELECT 1 FROM operational.offer_cycles cycle
                    WHERE cycle.business_id=scope.business_id AND cycle.company_id=requested.company_id
                      AND cycle.status='unknown')
            FROM requested CROSS JOIN scope
            LEFT JOIN LATERAL (
                SELECT first_presented_at FROM operational.recommendations
                WHERE business_id=scope.business_id AND company_id=requested.company_id
                  AND status='open'
            ) recommendation ON true
            ORDER BY requested.ordinal""",
            (business_id, as_of, exclude_offer_cycle_id, list(company_ids)),
        ).fetchall()
        return tuple(
            BusinessCompanyState(
                first_presented_at=row[1],
                cooldown_until=row[2],
                paused_until=row[3],
                paused_indefinitely=row[4],
                rejected=row[5],
                has_relationship=row[6],
                pending_delivery=row[7],
                uncertain_delivery=row[8],
            )
            for row in rows
        )


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()
