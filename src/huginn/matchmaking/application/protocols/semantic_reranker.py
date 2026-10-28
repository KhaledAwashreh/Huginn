from typing import Protocol

from huginn.matchmaking.application.read_models.semantic_relevance import (
    SemanticRelevance,
)


class SemanticReranker(Protocol):
    def rerank(self, query: str, documents: tuple[str, ...]) -> SemanticRelevance: ...
