from enum import StrEnum


class ActivityKind(StrEnum):
    PROSPECT_SAVED = "prospect_saved"
    STAGE_CHANGED = "stage_changed"
    CLOSED = "closed"
    REOPENED = "reopened"
    NOTE_ADDED = "note_added"
    FOLLOW_UP_SET = "follow_up_set"
    FOLLOW_UP_CLEARED = "follow_up_cleared"
    PROPOSAL_DRAFTED = "proposal_drafted"
    PROPOSAL_SENT = "proposal_sent"
    CORRECTION = "correction"
