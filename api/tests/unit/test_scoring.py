import pytest

from career_intel.analysis.scoring import ScoredRequirement, compute_overall_score


def test_all_strong_scores_one():
    assert compute_overall_score([ScoredRequirement("required", "strong")] * 3) == 1.0


def test_all_missing_scores_zero():
    assert compute_overall_score([ScoredRequirement("required", "missing")] * 3) == 0.0


def test_required_weighs_double_preferred():
    # required missing + preferred strong → 1.0 / 3.0
    items = [ScoredRequirement("required", "missing"), ScoredRequirement("preferred", "strong")]
    assert compute_overall_score(items) == pytest.approx(1 / 3)


def test_empty_scores_zero_rather_than_dividing_by_zero():
    assert compute_overall_score([]) == 0.0
