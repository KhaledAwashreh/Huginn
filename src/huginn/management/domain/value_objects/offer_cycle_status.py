from enum import StrEnum


class OfferCycleStatus(StrEnum):
    PREPARING = "preparing"
    SENDING = "sending"
    CONFIRMED = "confirmed"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"
