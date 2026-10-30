"""Optional CPU model adapter; research-ranking.md documents score semantics."""

import copy
import hashlib
import logging
import math
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from huginn.matchmaking.application.read_models.semantic_relevance import (
    SemanticRelevance,
)

logger = logging.getLogger(__name__)
MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


class FastEmbedSemanticReranker:
    def __init__(
        self,
        *,
        model_name: str = MODEL,
        cache_dir: str | None = None,
        threads: int = 2,
        max_documents: int = 200,
        max_document_chars: int = 200_000,
        max_passages: int = 1024,
        model_factory: Callable | None = None,
    ):
        if model_name != MODEL:
            raise ValueError("Only the pinned single-logit semantic model is supported")
        if type(threads) is not int or not 1 <= threads <= 8:
            raise ValueError("CPU threads must be between one and eight")
        if any(
            type(value) is not int or value < 1
            for value in (max_documents, max_document_chars, max_passages)
        ):
            raise ValueError("Semantic work bounds must be positive integers")
        injected = model_factory is not None
        if model_factory is None:
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder
            except ImportError as exc:
                raise RuntimeError(
                    "Install the optional ranking extra to use FastEmbed"
                ) from exc
            model_factory = TextCrossEncoder
        logger.info("Loading explicitly configured CPU semantic reranker")
        self._model = model_factory(
            model_name=model_name,
            cache_dir=cache_dir,
            threads=threads,
            providers=["CPUExecutionProvider"],
        )
        inner = getattr(self._model, "model", self._model)
        tokenizer = inner.tokenizer
        truncation = tokenizer.truncation
        if (
            not truncation
            or type(truncation.get("max_length")) is not int
            or truncation["max_length"] < 1
        ):
            raise ValueError(
                "Semantic tokenizer must expose its positive context limit"
            )
        self._limit = truncation["max_length"]
        self._tokenizer = copy.deepcopy(tokenizer)
        self._tokenizer.no_truncation()
        self._tokenizer.no_padding()
        try:
            package_version = version("fastembed")
        except PackageNotFoundError:
            package_version = "injected"
        asset_hash = "injected"
        if not injected:
            model_file = Path(inner._model_dir) / inner.model_description.model_file
            digest = hashlib.sha256()
            with model_file.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
            asset_hash = digest.hexdigest()
        token_hash = hashlib.sha256(tokenizer.to_str().encode()).hexdigest()
        self._reference = f"fastembed:{package_version}:{MODEL};weights={asset_hash};tokenizer={token_hash};char-max-v1"
        self._max_documents = max_documents
        self._max_document_chars = max_document_chars
        self._max_passages = max_passages

    def _fits(self, query: str, document: str) -> bool:
        return len(self._tokenizer.encode(query, document).ids) <= self._limit

    def _passages(self, query: str, document: str) -> list[str]:
        result = []
        start = 0
        while start < len(document):
            remaining = document[start:]
            if self._fits(query, remaining):
                result.append(remaining)
                break
            lo, hi, best = 1, len(remaining), 0
            while lo <= hi:
                middle = (lo + hi) // 2
                if self._fits(query, remaining[:middle]):
                    best = middle
                    lo = middle + 1
                else:
                    hi = middle - 1
            if best == 0:
                raise ValueError(
                    "Semantic query leaves no space for a document character"
                )
            result.append(remaining[:best])
            start += best
            if len(result) >= self._max_passages:
                raise ValueError("Semantic passage work limit exceeded")
        return result

    def rerank(self, query: str, documents: tuple[str, ...]) -> SemanticRelevance:
        if (
            type(query) is not str
            or not query.strip()
            or len(query) > 20_000
            or not self._fits(query, "")
        ):
            raise ValueError("Semantic query exceeds the model context or is empty")
        if (
            not isinstance(documents, tuple)
            or len(documents) > self._max_documents
            or any(
                type(doc) is not str
                or not doc.strip()
                or len(doc) > self._max_document_chars
                for doc in documents
            )
        ):
            raise ValueError("Semantic documents exceed work bounds or are empty")
        if sum(map(len, documents)) > 2_000_000:
            raise ValueError("Semantic total text work limit exceeded")
        passages, owners = [], []
        for index, document in enumerate(documents):
            chunks = self._passages(query, document)
            passages.extend(chunks)
            owners.extend([index] * len(chunks))
            if len(passages) > self._max_passages:
                raise ValueError("Semantic passage work limit exceeded")
        if not documents:
            return SemanticRelevance((), self._reference)
        logger.info(
            "Scoring %s semantic documents in %s complete-text passages",
            len(documents),
            len(passages),
        )
        raw = tuple(self._model.rerank(query, passages, batch_size=16))
        if len(raw) != len(passages) or any(
            type(score) not in (int, float) or not math.isfinite(score) for score in raw
        ):
            raise ValueError("Semantic provider returned invalid score count or values")
        scores = [float("-inf")] * len(documents)
        for owner, score in zip(owners, raw, strict=True):
            scores[owner] = max(scores[owner], float(score))
        return SemanticRelevance(tuple(scores), self._reference)
