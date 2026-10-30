from types import MappingProxyType

RESEARCH_RANKING_VERSION = "research-ranking-v1"
SEMANTIC_SERVICE_TRANSFORM = "sigmoid-to-40-v1"
SERVICE_POINTS = MappingProxyType(
    {"direct": 40, "plausible": 28, "adjacent": 12, "unknown": 0, "unrelated": 0}
)
CONTEXT_POINTS = MappingProxyType(
    {"explicit_change": 30, "specific_context": 20, "general_context": 10, "unknown": 0}
)
EVIDENCE_BASES = ("observed", "inferred", "unknown")
PREFERENCE_MATCHES = ("match", "mismatch", "unknown")
CONFIDENCE_ORDER = MappingProxyType({"high": 0, "medium": 1, "low": 2})
