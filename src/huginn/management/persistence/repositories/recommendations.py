"""Owner-scoped immutable recommendation history; architecture section 9."""

import json
import re
from datetime import datetime
from uuid import UUID

from huginn.management.application.protocols.recommendations import (
    RecommendationRepository,
)
from huginn.management.application.read_models.recommendation_company import (
    RecommendationCompany,
)
from huginn.management.application.read_models.recommendation_profile import (
    RecommendationProfile,
)
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.persistence.contracts.database import (
    DatabaseSession,
    JsonParameter,
)
from huginn.matchmaking.domain.value_objects.ranking_observation import (
    RankingObservation,
)


class PostgresRecommendationRepository(RecommendationRepository):
    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    def active_strategy_ids(self, user_id: UUID) -> tuple[UUID, ...]:
        return tuple(
            row[0]
            for row in self.connection.execute(
                """SELECT s.id FROM operational.client_discovery_strategies s
            JOIN operational.service_offerings o ON o.id=s.service_offering_id AND o.user_id=s.user_id
            JOIN operational.ideal_client_profiles i ON i.id=s.ideal_client_profile_id AND i.user_id=s.user_id
            JOIN operational.users u ON u.id=s.user_id
            JOIN operational.accounts a ON a.id=u.account_id
            WHERE s.user_id=%s AND s.is_active AND a.status='active' ORDER BY s.id""",
                (user_id,),
            ).fetchall()
        )

    def weekly_batches(self, user_id: UUID, limit: int, offset: int) -> tuple[str, ...]:
        return tuple(
            json.dumps(row[0])
            for row in self.connection.execute(
                """SELECT b.snapshot FROM operational.weekly_digest_deliveries d
            JOIN operational.recommendation_batches b ON b.id=d.batch_id AND b.user_id=d.user_id
            WHERE d.user_id=%s AND d.state IN ('sending','sent','unknown')
            ORDER BY d.week_start DESC,d.id DESC LIMIT %s OFFSET %s""",
                (user_id, limit, offset),
            ).fetchall()
        )

    def profile(self, user_id: UUID, strategy_id: UUID) -> RecommendationProfile | None:
        row = self.connection.execute(
            """SELECT s.id, jsonb_build_object(
                'strategy', to_jsonb(s), 'offering', to_jsonb(o),
                'icp', to_jsonb(i), 'professional_profile', to_jsonb(p)),
                o.name || E'\n' || o.description
            FROM operational.client_discovery_strategies s
            JOIN operational.service_offerings o ON o.id=s.service_offering_id AND o.user_id=s.user_id
            JOIN operational.ideal_client_profiles i ON i.id=s.ideal_client_profile_id AND i.user_id=s.user_id
            LEFT JOIN operational.professional_profiles p ON p.user_id=s.user_id
            WHERE s.user_id=%s AND s.id=%s AND s.is_active""",
            (user_id, strategy_id),
        ).fetchone()
        return (
            RecommendationProfile(row[0], json.dumps(row[1]), row[2]) if row else None
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
        patterns = [r"\m" + re.escape(term) + r"\M" for term in terms]
        rows = self.connection.execute(
            """WITH eligible AS MATERIALIZED (
                SELECT company_id, observation_id, description, occurred_at, observed_at, source, source_url, source_country
                FROM gold.current_source_evidence
                WHERE (occurred_at IS NULL OR occurred_at BETWEEN %s AND %s)
                  AND (observed_at IS NULL OR observed_at <= %s)
                  AND NOT (company_id = ANY(%s::uuid[]))
            ), selected AS (
                SELECT e.company_id, count(DISTINCT term) AS hits
                FROM eligible e CROSS JOIN unnest(%s::text[]) AS term
                WHERE e.description ~* term
                GROUP BY e.company_id ORDER BY hits DESC, e.company_id LIMIT %s OFFSET %s
            )
            SELECT c.id,c.name,c.domain,c.business_sector,c.country,c.company_scale,
                e.observation_id,e.description,e.occurred_at,e.observed_at,e.source,e.source_url,e.source_country
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

    def save_batch(
        self,
        user_id: UUID,
        batch_id: UUID,
        strategy_id: UUID,
        created_at: datetime,
        snapshot_json: str,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO operational.recommendation_batches(id,user_id,strategy_id,created_at,snapshot) VALUES (%s,%s,%s,%s,%s)",
                (
                    batch_id,
                    user_id,
                    strategy_id,
                    created_at,
                    JsonParameter(json.loads(snapshot_json)),
                ),
            )

    def get_batch(self, user_id: UUID, batch_id: UUID) -> str | None:
        row = self.connection.execute(
            "SELECT snapshot FROM operational.recommendation_batches WHERE user_id=%s AND id=%s",
            (user_id, batch_id),
        ).fetchone()
        return json.dumps(row[0]) if row else None

    def latest_batch(self, user_id: UUID, strategy_id: UUID) -> str | None:
        row = self.connection.execute(
            "SELECT snapshot FROM operational.recommendation_batches WHERE user_id=%s AND strategy_id=%s AND COALESCE(snapshot->'batch'->>'kind','on_demand')='on_demand' ORDER BY created_at DESC,id DESC LIMIT 1",
            (user_id, strategy_id),
        ).fetchone()
        return json.dumps(row[0]) if row else None

    def append_feedback(
        self,
        user_id: UUID,
        batch_id: UUID,
        feedback_id: UUID,
        recommendation_id: str,
        created_at: datetime,
        payload_json: str,
    ) -> None:
        row = self.connection.execute(
            """INSERT INTO operational.recommendation_feedback(id,user_id,batch_id,recommendation_id,created_at,payload)
            SELECT %s,%s,%s,%s,%s,%s WHERE EXISTS (
                SELECT 1 FROM operational.recommendation_batches WHERE id=%s AND user_id=%s
            ) RETURNING id""",
            (
                feedback_id,
                user_id,
                batch_id,
                recommendation_id,
                created_at,
                JsonParameter(json.loads(payload_json)),
                batch_id,
                user_id,
            ),
        ).fetchone()
        if row is None:
            raise NotFoundError("Recommendation batch not found")

    def feedback(self, user_id: UUID, batch_id: UUID) -> tuple[str, ...]:
        rows = self.connection.execute(
            "SELECT payload FROM operational.recommendation_feedback WHERE user_id=%s AND batch_id=%s ORDER BY created_at,id",
            (user_id, batch_id),
        ).fetchall()
        return tuple(json.dumps(row[0]) for row in rows)
