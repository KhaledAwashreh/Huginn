from types import SimpleNamespace
from unittest.mock import patch

import pytest

from huginn.matchmaking.application.read_models.semantic_relevance import (
    SemanticRelevance,
)
from huginn.matchmaking.infrastructure.fastembed_semantic_reranker import (
    FastEmbedSemanticReranker,
)


class Tokenizer:
    truncation = {"max_length": 12}
    padding = None

    def no_truncation(self):
        self.truncation = None

    def no_padding(self):
        self.padding = None

    def encode(self, query, document=None):
        if not isinstance(query, str) or not isinstance(document, str):
            raise TypeError(
                "encode expects sequence and pair as separate text arguments"
            )
        return SimpleNamespace(ids=list(range(len(query) + len(document) + 3)))

    def to_str(self):
        return "synthetic-tokenizer"


class Model:
    tokenizer = Tokenizer()

    def __init__(self):
        self.calls = []

    def rerank(self, query, documents, batch_size):
        self.calls.append((query, list(documents)))
        return [float(len(document)) - 5 for document in documents]


def adapter(model=None, **kwargs):
    model = model or Model()
    return FastEmbedSemanticReranker(
        model_factory=lambda **options: model, **kwargs
    ), model


def test_chunks_preserve_every_character_and_aggregate_max_in_original_order():
    instance, model = adapter()
    result = instance.rerank("q", ("12345678901234567890", "abc"))
    assert result.logits == (3.0, -2.0)
    passages = [part for _, parts in model.calls for part in parts]
    assert "".join(passages[:-1]) == "12345678901234567890"
    assert all(len("q") + len(part) + 3 <= 12 for part in passages)
    assert "char-max-v1" in result.model_reference
    assert model.tokenizer.truncation == {"max_length": 12}


def test_oversize_query_rejected_before_scoring():
    instance, model = adapter()
    with pytest.raises(ValueError, match="query"):
        instance.rerank("x" * 12, ("text",))
    assert model.calls == []


@pytest.mark.parametrize("scores", [[1.0], [1.0, float("nan")], [1.0, float("inf")]])
def test_bad_provider_count_or_nonfinite_rejected(scores):
    model = Model()
    model.rerank = lambda *args, **kwargs: scores
    instance, _ = adapter(model)
    with pytest.raises(ValueError):
        instance.rerank("q", ("abc", "def"))


def test_input_and_work_bounds():
    instance, _ = adapter(max_documents=1, max_document_chars=10, max_passages=1)
    with pytest.raises(ValueError):
        instance.rerank("q", ("abc", "def"))
    with pytest.raises(ValueError):
        instance.rerank("q", ("x" * 11,))
    with pytest.raises(ValueError):
        instance.rerank("q", ("x" * 10,))


def test_only_pinned_model_and_bounded_cpu_threads():
    for kwargs in ({"model_name": "unknown"}, {"threads": 0}, {"threads": 20}):
        with pytest.raises(ValueError):
            adapter(**kwargs)


def test_empty_batch_returns_no_fabricated_scores():
    instance, model = adapter()
    assert instance.rerank("q", ()).logits == ()
    assert model.calls == []


def test_semantic_projection_rejects_invalid_numbers_and_reference():
    for values in ((True,), (float("nan"),), [1.0]):
        with pytest.raises(ValueError):
            SemanticRelevance(values, "model")
    with pytest.raises(ValueError):
        SemanticRelevance((), "")


def test_optional_dependency_error_does_not_attempt_model_download():
    import builtins

    original_import = builtins.__import__

    def without_fastembed(name, *args, **kwargs):
        if name.startswith("fastembed"):
            raise ImportError("optional package deliberately unavailable")
        return original_import(name, *args, **kwargs)

    with (
        patch("builtins.__import__", side_effect=without_fastembed),
        pytest.raises(RuntimeError, match="optional ranking extra"),
    ):
        FastEmbedSemanticReranker()
