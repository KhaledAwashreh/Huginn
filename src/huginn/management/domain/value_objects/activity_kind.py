from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ActivityKind:
    value: Literal[
        "prospect_saved",
        "stage_changed",
        "closed",
        "reopened",
        "note_added",
        "follow_up_set",
        "follow_up_cleared",
        "proposal_drafted",
        "proposal_sent",
        "correction",
    ]

    def __post_init__(self) -> None:
        if self.value not in {
            "prospect_saved",
            "stage_changed",
            "closed",
            "reopened",
            "note_added",
            "follow_up_set",
            "follow_up_cleared",
            "proposal_drafted",
            "proposal_sent",
            "correction",
        }:
            raise ValueError("invalid activity kind")
