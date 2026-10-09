from dataclasses import dataclass


@dataclass(frozen=True)
class StageDescriptor:
    name: str
    order: int
    dependencies: tuple[str, ...]
    group: str
    source_children: tuple[str, ...] = ()
