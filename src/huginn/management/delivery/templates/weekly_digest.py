"""Plain-text rendering of immutable recommendation revisions for SMTP."""

from datetime import date
from uuid import UUID

from huginn.management.application.read_models.digest_subscription import (
    DigestSubscription,
)
from huginn.management.application.read_models.weekly_digest_message import (
    WeeklyDigestMessage,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.security.digest_unsubscribe import digest_unsubscribe_token


class PlainTextWeeklyDigestRenderer:
    def __init__(self, web_origin: str, signing_key: str, sender_domain: str) -> None:
        if not web_origin or not signing_key or not sender_domain:
            raise ValueError("Digest renderer requires trusted origin and signing key")
        self._origin = web_origin.rstrip("/")
        self._signing_key = signing_key
        self._sender_domain = sender_domain

    def render(
        self,
        subscription: DigestSubscription,
        week_start: date,
        content_id: UUID,
        revisions: tuple[AssessmentRevision, ...],
    ) -> WeeklyDigestMessage:
        if type(week_start) is not date or week_start.weekday() != 0:
            raise ValueError("Digest rendering requires Monday week start")
        if not revisions or len(revisions) > 7:
            raise ValueError("Digest rendering requires one to seven revisions")
        unsubscribe_token = digest_unsubscribe_token(
            self._signing_key,
            subscription.user_id,
            subscription.recipient,
            subscription.version,
        )
        unsubscribe_url = (
            f"{self._origin}/weekly-digest/unsubscribe"
            f"#user_id={subscription.user_id}&token={unsubscribe_token}"
        )
        lines = [
            f"Your Huginn Weekly Recommendations — week of {week_start.isoformat()}",
            "",
            "These are research ideas, not confirmed buying intent.",
            "",
        ]
        seen_companies: set[UUID] = set()
        for position, revision in enumerate(revisions, 1):
            if revision.company_id in seen_companies:
                raise ValueError("Digest revisions must contain distinct Companies")
            seen_companies.add(revision.company_id)
            company_facts = _company_facts(revision)
            lines.append(
                f"{position}. {_line(company_facts.get('name') or 'Company')} "
                f"({_line(company_facts.get('domain') or 'Unknown domain')})"
            )
            for association in revision.strategy_assessments:
                snapshot = association.assessment_snapshot.to_json_object()
                score = snapshot.get("score")
                confidence = snapshot.get("confidence")
                rationale = _line(snapshot.get("rationale") or "")
                lines.append(
                    f"Strategy: {_line(association.strategy_snapshot.to_json_object().get('name') or 'Discovery strategy')} — "
                    f"{_line(association.offering_snapshot.to_json_object().get('name') or 'Service offering')}"
                )
                lines.append(
                    f"Strategy relevance: {score}/100; confidence: {confidence}"
                )
                if rationale:
                    lines.append(rationale)
                unknowns = snapshot.get("unknowns", ())
                if unknowns:
                    lines.append(
                        "Still unknown: "
                        + "; ".join(_line(value) for value in unknowns)
                    )
                for evidence in _grounded_evidence(revision, snapshot):
                    lines.extend(
                        (
                            f"Source: {_line(evidence.get('quote') or '')}",
                            "Source date: "
                            + _line(evidence.get("occurred_at") or "Unknown"),
                            _line(evidence.get("source_url") or ""),
                        )
                    )
            recommendation_url = (
                f"{self._origin}/recommendations?recommendation_id="
                f"{revision.recommendation_id}&assessment_revision_id={revision.id}"
            )
            lines.extend((f"Review this recommendation: {recommendation_url}", ""))
        lines.extend((f"Stop weekly digests: {unsubscribe_url}", ""))
        body = "\n".join(lines).replace("\r\n", "\n").replace("\r", "\n")
        return WeeklyDigestMessage(
            subscription.recipient,
            f"Huginn: your Weekly Recommendations ({week_start.isoformat()})",
            body,
            f"<weekly-{content_id}@{self._sender_domain}>",
        )


def _company_facts(revision: AssessmentRevision) -> dict:
    for association in revision.strategy_assessments:
        facts = association.assessment_snapshot.to_json_object().get("company_facts")
        if isinstance(facts, dict):
            return facts
    return {}


def _grounded_evidence(
    revision: AssessmentRevision, assessment: dict
) -> tuple[dict, ...]:
    accepted = {str(value) for value in revision.evidence_observation_ids}
    snapshots = {}
    for snapshot in revision.evidence_snapshots:
        value = snapshot.to_json_object()
        observation_id = value.get("observation_id")
        if observation_id is not None and str(observation_id) in accepted:
            snapshots[str(observation_id)] = value
    retained = []
    for evidence in assessment.get("evidence", ()):
        if not isinstance(evidence, dict):
            continue
        observation_id = evidence.get("observation_id")
        snapshot = (
            snapshots.get(str(observation_id)) if observation_id is not None else None
        )
        if snapshot is not None:
            retained.append({**evidence, **snapshot})
    return tuple(retained[:1])


def _line(value: object) -> str:
    return " ".join(str(value).split())
