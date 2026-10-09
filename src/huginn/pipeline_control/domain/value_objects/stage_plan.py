from dataclasses import dataclass

from huginn.pipeline_control.domain.value_objects.stage_descriptor import (
    StageDescriptor,
)


@dataclass(frozen=True)
class StagePlan:
    stages: tuple[StageDescriptor, ...]

    def __post_init__(self) -> None:
        names = tuple(stage.name for stage in self.stages)
        if len(names) != len(set(names)):
            raise ValueError("stage names must be unique")
        if tuple(stage.order for stage in self.stages) != tuple(
            range(len(self.stages))
        ):
            raise ValueError("stage order must be contiguous and zero-based")
        known = set(names)
        if any(not set(stage.dependencies) <= known for stage in self.stages):
            raise ValueError("stage dependencies must reference stages in the plan")

    def to_json(self) -> list[dict[str, object]]:
        return [
            {
                "name": stage.name,
                "order": stage.order,
                "dependencies": list(stage.dependencies),
                "group": stage.group,
                "source_children": list(stage.source_children),
            }
            for stage in self.stages
        ]

    @classmethod
    def from_json(cls, value: object) -> StagePlan:
        if not isinstance(value, list):
            raise ValueError("stage plan must be a list")
        stages: list[StageDescriptor] = []
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("stage plan entries must be objects")
            stages.append(
                StageDescriptor(
                    name=str(item["name"]),
                    order=int(item["order"]),
                    dependencies=tuple(str(name) for name in item["dependencies"]),
                    group=str(item["group"]),
                    source_children=tuple(
                        str(name) for name in item.get("source_children", [])
                    ),
                )
            )
        return cls(tuple(stages))


SUPPORTED_STAGE_PLAN = StagePlan(
    (
        StageDescriptor("ingestion", 0, (), "source", ("hn", "yc")),
        StageDescriptor("ingestion.eu_startups", 1, (), "source", ("eu_startups",)),
        StageDescriptor("silver.hn_staging", 2, ("ingestion",), "silver"),
        StageDescriptor("silver.yc_staging", 3, ("ingestion",), "silver"),
        StageDescriptor(
            "silver.eu_startups_staging", 4, ("ingestion.eu_startups",), "silver"
        ),
        StageDescriptor(
            "silver.signal_resolution",
            5,
            ("silver.hn_staging", "silver.yc_staging", "silver.eu_startups_staging"),
            "silver",
        ),
        StageDescriptor(
            "silver.manual_review", 6, ("silver.signal_resolution",), "silver"
        ),
        StageDescriptor("gold.company", 7, ("silver.signal_resolution",), "gold"),
        StageDescriptor(
            "gold.company_signal",
            8,
            ("silver.signal_resolution", "gold.company"),
            "gold",
        ),
    )
)
