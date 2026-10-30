"""Choose seven distinct companies across strategy assessments without score inflation."""

from copy import deepcopy


def select_weekly_matches(items: list[dict]) -> list[dict]:
    ordered = sorted(
        items,
        key=lambda item: (
            -item["score"],
            {"high": 0, "medium": 1, "low": 2}[item["confidence"]],
            item["company"]["id"],
            item["id"],
        ),
    )
    companies = {}
    for original in ordered:
        item = deepcopy(original)
        for strategy in item["strategies"]:
            strategy.update(
                score=item["score"],
                rationale=item["rationale"],
                evidence=deepcopy(item["evidence"]),
            )
        identifier = item["company"]["id"]
        if identifier not in companies:
            companies[identifier] = deepcopy(item)
            companies[identifier]["selection_type"] = "exploitation"
        else:
            current = companies[identifier]["strategies"]
            current.extend(
                deepcopy(strategy)
                for strategy in item["strategies"]
                if strategy["id"] not in {value["id"] for value in current}
            )
    return list(companies.values())[:7]
