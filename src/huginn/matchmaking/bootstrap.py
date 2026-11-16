"""Explicit, inert composition, matchmaking design section 9."""

from huginn.matchmaking.application.errors.retired import MatchmakingRetiredError


def build_service(config=None):
    """Fail closed: the legacy Match creation workflow is retired."""
    del config
    raise MatchmakingRetiredError


def build_batch_service(config=None):
    """Fail closed: batch Match creation is retired as well."""
    del config
    raise MatchmakingRetiredError
