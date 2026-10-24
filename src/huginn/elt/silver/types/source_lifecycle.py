from typing import Literal

ListingState = Literal["available", "withdrawn", "invalid", "unknown"]
HiringState = Literal["true", "false", "unknown", "not_applicable"]
IdentityState = Literal["consistent", "unresolved", "mismatch", "missing"]
