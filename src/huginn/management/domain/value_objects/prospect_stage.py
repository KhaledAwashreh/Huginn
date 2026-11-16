from enum import StrEnum


class ProspectStage(StrEnum):
    SAVED = "saved"
    CONTACTED = "contacted"
    IN_CONVERSATION = "in_conversation"
    PROPOSAL_SENT = "proposal_sent"
    WON_CLIENT = "won_client"
    CLOSED = "closed"
