"""Score calibration: turn a cosine similarity into a decision and a %.

SFace outputs unit-length 128-d vectors, so the raw comparison is a cosine
similarity in ``[-1, 1]``.  On the calibration set (public-domain portraits of
the same people taken 3-11 years apart, different clothes, backgrounds and
lighting) the observed ranges are:

    same person       0.55 … 0.81
    different people -0.09 … 0.16

The presets below sit in that gap and leave head-room on both sides.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

from .config import THRESHOLD_PRESETS, resolve_threshold

#: Score at which the logistic confidence curve is at 50 %.
CONFIDENCE_MIDPOINT = 0.335

#: Steepness of the logistic curve (higher = more decisive).
CONFIDENCE_SLOPE = 0.055


def resolve_profile(threshold: Optional[object], fallback: float = 0.40) -> Tuple[float, str]:
    """Return ``(cutoff, profile_name)`` for a threshold name, number or ``None``."""
    if threshold is None:
        cutoff = float(fallback)
        name = next(
            (k for k, v in THRESHOLD_PRESETS.items() if abs(v - cutoff) < 1e-9), "custom"
        )
        return cutoff, name

    if isinstance(threshold, str):
        name = threshold.strip().lower()
        return resolve_threshold(name), (name if name in THRESHOLD_PRESETS else "custom")

    return resolve_threshold(threshold), "custom"


def confidence_from_score(score: float, threshold: float = 0.40) -> float:
    """Map a similarity to a 0..1 confidence, nudged by the active threshold.

    The result is *not* a probability that two people are the same in the
    statistical sense; it is a calibrated readability aid that always agrees
    with the boolean decision (a score at the threshold gives ≈ 0.75, a score
    one full threshold-margin away saturates).
    """
    logistic = 1.0 / (1.0 + math.exp(-(score - CONFIDENCE_MIDPOINT) / CONFIDENCE_SLOPE))

    # Blend with a margin-based term so the number tracks the active policy.
    margin = (score - threshold) / max(threshold, 1e-6)
    margin_term = 1.0 / (1.0 + math.exp(-margin * 6.0))

    value = 0.65 * logistic + 0.35 * margin_term
    value = max(0.0, min(1.0, value))
    # Keep the boolean and the percentage consistent.
    if score >= threshold:
        return max(value, 0.5)
    return min(value, 0.499)


def describe_score(score: float) -> str:
    """Human-readable band for a raw similarity score."""
    if score >= 0.55:
        return "very strong match"
    if score >= 0.48:
        return "strong match"
    if score >= 0.40:
        return "match"
    if score >= 0.33:
        return "weak match"
    if score >= 0.20:
        return "probably different people"
    return "different people"


def adaptive_threshold(
    gallery_scores: list[float],
    base_threshold: float,
    *,
    max_relax: float = 0.035,
) -> float:
    """Adjust the threshold for how tightly an identity's own photos agree.

    If a person's enrolled photos already score 0.9 against each other, their
    live photos will look very similar too, and the threshold can stay strict.
    If enrollment photos score 0.6 against each other (glasses on/off, beard,
    ten years apart), a stricter-than-needed threshold would lock them out —
    so we relax slightly, but never by more than ``max_relax``.
    """
    if not gallery_scores:
        return base_threshold
    observed = sum(gallery_scores) / len(gallery_scores)
    gap = max(0.0, 0.72 - observed)      # head-room we may use
    relax = min(max_relax, gap * 0.5)    # only part of the head-room
    floor = max(0.30, base_threshold - max_relax)
    return float(max(floor, base_threshold - relax))


__all__ = [
    "CONFIDENCE_MIDPOINT",
    "CONFIDENCE_SLOPE",
    "resolve_profile",
    "confidence_from_score",
    "describe_score",
    "adaptive_threshold",
]
