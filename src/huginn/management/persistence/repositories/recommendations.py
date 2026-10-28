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
    ) -> tuple[RecommendationCompany, ...]:
        if cutoff.tzinfo is None or as_of.tzinfo is None or cutoff > as_of:
            raise ValueError("invalid recommendation evidence window")
        if not 1 <= limit <= 200:
            raise ValueError("candidate limit must be between 1 and 200")
        terms = tuple(sorted({term.lower() for term in terms if term.strip()}))
        if not terms:
            return ()
        patterns = [r"\m" + re.escape(term) + r"\M" for term in terms]
        rows = self.connection.execute(
            """WITH eligible AS MATERIALIZED (
                SELECT company_id, observation_id, description, occurred_at, observed_at, source, source_url
                FROM gold.current_source_evidence
                WHERE (occurred_at IS NULL OR occurred_at BETWEEN %s AND %s)
                  AND (observed_at IS NULL OR observed_at <= %s)
            ), selected AS (
                SELECT e.company_id, count(DISTINCT term) AS hits
                FROM eligible e CROSS JOIN unnest(%s::text[]) AS term
                WHERE e.description ~* term
                GROUP BY e.company_id ORDER BY hits DESC, e.company_id LIMIT %s
            )
            SELECT c.id,c.name,c.domain,c.business_sector,c.country,c.company_scale,
                e.observation_id,e.description,e.occurred_at,e.observed_at,e.source,e.source_url
            FROM selected s JOIN gold.company c ON c.id=s.company_id
            JOIN eligible e ON e.company_id=c.id
            ORDER BY s.hits DESC,c.id,e.occurred_at NULLS LAST,e.observation_id""",
            (cutoff, as_of, as_of, patterns, limit),
        ).fetchall()
        grouped: dict[UUID, list] = {}
        metadata: dict[UUID, tuple] = {}
        for row in rows:
            metadata[row[0]] = row[:6]
            grouped.setdefault(row[0], []).append(RankingObservation(*row[6:]))
        return tuple(
            RecommendationCompany(
                *metadata[key][:3],
                tuple(metadata[key][3]) if metadata[key][3] is not None else None,
                *metadata[key][4:],
                tuple(observations),
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
            "SELECT snapshot FROM operational.recommendation_batches WHERE user_id=%s AND strategy_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
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
