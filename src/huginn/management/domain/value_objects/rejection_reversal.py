from dataclasses import dataclass


@dataclass(frozen=True)
class RejectionReversal:
    clear_rejection: bool = True
    reopen_recommendation: bool = False
    generate_recommendation: bool = False
