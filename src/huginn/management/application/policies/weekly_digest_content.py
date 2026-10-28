"""Plain research-digest content, docs/weekly-digest.md."""

from datetime import date


def weekly_digest_body(
    batch: dict, week: date, batch_url: str, unsubscribe_url: str
) -> str:
    lines = [
        f"Your Huginn research picks — week of {week.isoformat()}",
        "",
        "These are research ideas, not confirmed buying intent.",
        "",
    ]
    for index, item in enumerate(batch["items"], 1):
        company = item["company"]
        lines.extend(
            (
                f"{index}. {company['name']} ({company['domain']})",
                f"Research relevance: {item['score']}/100",
                item["rationale"],
            )
        )
        for evidence in item["evidence"][:1]:
            lines.extend((f"Source: {evidence['quote']}", f"{evidence['source_url']}"))
        lines.append("")
    lines.extend(
        (
            f"Review these saved recommendations and give feedback: {batch_url}",
            "",
            f"Stop weekly digests: {unsubscribe_url}",
            "",
        )
    )
    return "\n".join(lines)
