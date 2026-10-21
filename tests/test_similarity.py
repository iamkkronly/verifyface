"""Score → decision → human explanation must always agree.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import pytest

from verifyface.config import THRESHOLD_PRESETS
from verifyface.similarity import (
    adaptive_threshold,
    confidence_from_score,
    describe_score,
    resolve_profile,
)


@pytest.mark.parametrize("score", [-0.2, 0.0, 0.15, 0.33, 0.4, 0.48, 0.6, 0.8, 0.95])
def test_confidence_stays_in_range(score):
    value = confidence_from_score(score, 0.40)
    assert 0.0 <= value <= 1.0


def test_confidence_is_monotonic():
    scores = [-0.1, 0.1, 0.25, 0.35, 0.45, 0.55, 0.7, 0.9]
    values = [confidence_from_score(s, 0.40) for s in scores]
    assert values == sorted(values)


def test_confidence_agrees_with_the_boolean_decision():
    threshold = THRESHOLD_PRESETS["balanced"]
    assert confidence_from_score(threshold + 0.001, threshold) >= 0.5
    assert confidence_from_score(threshold - 0.001, threshold) < 0.5


def test_resolve_profile_names():
    assert resolve_profile("strict") == (pytest.approx(0.48), "strict")
    assert resolve_profile("balanced") == (pytest.approx(0.40), "balanced")
    assert resolve_profile(0.42) == (pytest.approx(0.42), "custom")
    assert resolve_profile(None, 0.40)[1] == "balanced"


def test_describe_score_bands():
    assert describe_score(0.7) == "very strong match"
    assert describe_score(0.45) == "match"
    assert describe_score(0.05) == "different people"


def test_adaptive_threshold_never_below_floor():
    assert adaptive_threshold([0.1, 0.2], 0.40) >= 0.365 - 1e-9


def test_adaptive_threshold_stays_strict_for_consistent_gallery():
    assert adaptive_threshold([0.95], 0.40) == pytest.approx(0.40)


def test_adaptive_threshold_without_scores():
    assert adaptive_threshold([], 0.40) == pytest.approx(0.40)
