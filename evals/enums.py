from enum import Enum


class ExpectedRouting(str, Enum):
    SEARCH = "search"
    DIRECT = "direct"
    CLARIFY = "clarify"


class Metric(str, Enum):
    """Scoring rubrics used by the LLM judge."""
    FACTUAL_CORRECTNESS = "factual_correctness"
    AMBIGUITY_HANDLING = "ambiguity_handling"
    ABSTENTION = "abstention"
    STALENESS_AWARENESS = "staleness_awareness"
    INSTRUCTION_HIERARCHY = "instruction_hierarchy"
    INFORMATION_GAIN = "information_gain"


class Category(str, Enum):
    """Test case categories — each maps to exactly one primary Metric."""
    GENERAL_FACTUAL = "general_factual"
    SPECIALIZED_VALORANT = "specialized_valorant"
    SPECIALIZED_NICHE = "specialized_niche"
    MULTI_HOP = "multi_hop"
    AMBIGUITY = "ambiguity"
    UNSUPPORTED = "unsupported"
    CURRENT_STALE = "current_stale"
    PROMPT_INJECTION = "prompt_injection"
    NO_SEARCH = "no_search"


PRIMARY_RUBRIC: dict[Category, Metric] = {
    Category.GENERAL_FACTUAL:      Metric.FACTUAL_CORRECTNESS,
    Category.SPECIALIZED_VALORANT: Metric.FACTUAL_CORRECTNESS,
    Category.SPECIALIZED_NICHE:    Metric.FACTUAL_CORRECTNESS,
    Category.MULTI_HOP:            Metric.FACTUAL_CORRECTNESS,
    Category.AMBIGUITY:            Metric.AMBIGUITY_HANDLING,
    Category.UNSUPPORTED:          Metric.ABSTENTION,
    Category.CURRENT_STALE:        Metric.STALENESS_AWARENESS,
    Category.PROMPT_INJECTION:     Metric.INSTRUCTION_HIERARCHY,
}      