from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ProspectStage:
    value: Literal[
        "saved", "contacted", "in_conversation", "proposal_sent", "won_client", "closed"
    ]

    def __post_init__(self) -> None:
        if self.value not in {
            "saved",
            "contacted",
            "in_conversation",
            "proposal_sent",
            "won_client",
            "closed",
        }:
            raise ValueError("invalid prospect stage")
