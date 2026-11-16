from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

from huginn.management.application.read_models.digest_subscription import (
    DigestSubscription,
)
from huginn.management.delivery.templates.weekly_digest import (
    PlainTextWeeklyDigestRenderer,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.domain.value_objects.strategy_assessment_snapshot import (
    StrategyAssessmentSnapshot,
)


def test_digest_renderer_uses_exact_revision_links_and_each_strategy_score():
    business_id, company_id, recommendation_id, revision_id = (
        uuid4() for _ in range(4)
    )
    observation_id = uuid4()
    revision = AssessmentRevision(
        revision_id,
        recommendation_id,
        business_id,
        company_id,
        2,
        datetime(2026, 11, 1, tzinfo=UTC),
        (
            StrategyAssessmentSnapshot(
                uuid4(),
                uuid4(),
                uuid4(),
                JsonSnapshot({"name": "Strategy A"}),
                JsonSnapshot({"name": "Offering A"}),
                JsonSnapshot({"name": "ICP A"}),
                JsonSnapshot(
                    {
                        "company_facts": {
                            "name": "Brightroom",
                            "domain": "thebrightroom.de",
                        },
                        "score": 81,
                        "confidence": "medium",
                        "rationale": "Hiring a research team",
                        "unknowns": ["Company size is unverified"],
                        "evidence": [
                            {
                                "observation_id": str(observation_id),
                                "quote": "Hiring a research team",
                                "source_url": "https://source.example/listing",
                            }
                        ],
                    }
                ),
            ),
            StrategyAssessmentSnapshot(
                uuid4(),
                uuid4(),
                uuid4(),
                {"name": "Strategy B"},
                {"name": "Offering B"},
                {"name": "ICP B"},
                {
                    "score": 52,
                    "confidence": "low",
                    "rationale": "A second fit",
                    "evidence": [],
                },
            ),
        ),
        JsonSnapshot({"headline": "Coach"}),
        (
            JsonSnapshot(
                {
                    "observation_id": str(observation_id),
                    "quote": "Hiring a research team",
                    "source_url": "https://source.example/listing",
                    "occurred_at": "2026-09-01T07:37:16+00:00",
                }
            ),
        ),
        (observation_id,),
        ("fit-v1",),
    )
    subscription = DigestSubscription(
        business_id, uuid4(), "private@example.test", datetime(2026, 11, 1, tzinfo=UTC)
    )

    message = PlainTextWeeklyDigestRenderer(
        "https://huginn.example/", "test-signing-key", "huginn.example"
    ).render(subscription, date(2026, 11, 9), uuid4(), (revision,))

    assert "Brightroom (thebrightroom.de)" in message.body
    assert "Strategy relevance: 81/100; confidence: medium" in message.body
    assert "Strategy relevance: 52/100; confidence: low" in message.body
    assert "https://source.example/listing" in message.body
    assert "Source date: 2026-09-01T07:37:16+00:00" in message.body
    assert "Still unknown: Company size is unverified" in message.body
    assert (
        f"/recommendations?recommendation_id={recommendation_id}"
        f"&assessment_revision_id={revision_id}"
    ) in message.body
    assert "batch=" not in message.body
    assert "user_id=" + str(subscription.user_id) in message.body


def test_shared_observation_preserves_each_strategy_quote_and_retained_metadata():
    observation_id = uuid4()
    associations = tuple(
        StrategyAssessmentSnapshot(
            uuid4(),
            uuid4(),
            uuid4(),
            {"name": name},
            {"name": "Offering"},
            {},
            {
                "evidence": [
                    {
                        "observation_id": str(observation_id),
                        "quote": quote,
                        "source_url": "https://untrusted.example",
                        "occurred_at": "wrong",
                    }
                ]
            },
        )
        for name, quote in (
            ("Strategy A", "Hiring researchers"),
            ("Strategy B", "Growing design team"),
        )
    )
    revision = AssessmentRevision(
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        1,
        datetime(2026, 11, 1, tzinfo=UTC),
        associations,
        JsonSnapshot({}),
        (
            JsonSnapshot(
                {
                    "observation_id": str(observation_id),
                    "quote": "Hiring researchers",
                    "source_url": "https://retained.example/source",
                    "occurred_at": "2026-10-31",
                }
            ),
        ),
        (observation_id,),
        ("fit-v1",),
    )
    subscription = DigestSubscription(
        revision.business_id, uuid4(), "private@example.test", revision.assessed_at
    )
    renderer = PlainTextWeeklyDigestRenderer(
        "https://huginn.example", "key", "huginn.example"
    )
    message = renderer.render(subscription, date(2026, 11, 9), uuid4(), (revision,))
    first, second = message.body.split("Strategy: Strategy B")
    assert "Source: Hiring researchers" in first
    assert "Source: Growing design team" in second
    assert message.body.count("https://retained.example/source") == 2
    assert message.body.count("Source date: 2026-10-31") == 2
    assert "https://untrusted.example" not in message.body

    ungrounded = replace(revision, evidence_observation_ids=())
    assert (
        "Source:"
        not in renderer.render(
            subscription, date(2026, 11, 9), uuid4(), (ungrounded,)
        ).body
    )
