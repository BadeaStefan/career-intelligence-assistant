from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

VERDICT_WEIGHT = {"strong": 1.0, "partial": 0.5, "missing": 0.0}
IMPORTANCE_WEIGHT = {"required": 2.0, "preferred": 1.0}


@dataclass(frozen=True)
class ScoredRequirement:
    importance: Literal["required", "preferred"]
    verdict: Literal["strong", "partial", "missing"]


def compute_overall_score(items: Sequence[ScoredRequirement]) -> float:
    """Compute overall score as weighted average.

    Formula: Σ(importance_weight × verdict_weight) / Σ(importance_weight)

    Returns 0.0 for empty input instead of dividing by zero.

    Args:
        items: Sequence of ScoredRequirement items

    Returns:
        A float between 0.0 and 1.0 representing the overall score
    """
    if not items:
        return 0.0

    total_weighted_score = 0.0
    total_importance = 0.0

    for item in items:
        importance_w = IMPORTANCE_WEIGHT[item.importance]
        verdict_w = VERDICT_WEIGHT[item.verdict]

        total_weighted_score += importance_w * verdict_w
        total_importance += importance_w

    return total_weighted_score / total_importance
