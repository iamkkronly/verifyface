"""Liveness: make sure a real, present person is in front of the camera.

Two independent layers are used for live scans:

**Challenge–response (active)**
    The user is asked to perform two random actions — turn left, turn right,
    nod, move closer or blink.  The landmarks from YuNet are tracked across
    frames to confirm each action actually happened.  A printed photo cannot
    turn its head.

**Passive screen-replay heuristics**
    Screens and printed photos show measurable artefacts: reduced high-frequency
    detail, regular moiré patterns in the spectrum, and blown-out specular
    highlights.  We score them and reject the worst cases.

Honest limits
-------------
This is *not* a certified Presentation Attack Detection (PAD) system, and no
open-source library can promise bank-grade anti-spoofing with a single RGB
camera.  Use it for convenience logins, attendance and kiosks — and add a
second factor (OTP, PIN) for high-value actions.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .imageio import load_image
from .preprocess import DetectedFace, _estimate_pose

#: Everything a challenge can ask for.
ACTIONS: Dict[str, str] = {
    "turn_left": "Turn your head slowly to your left",
    "turn_right": "Turn your head slowly to your right",
    "nod": "Nod your head once",
    "come_closer": "Move a little closer to the camera",
    "blink": "Blink twice",
}

_DEFAULT_POOL = ("turn_left", "turn_right", "nod", "come_closer", "blink")


@dataclass
class LivenessReport:
    """Result of a liveness session."""

    passed: bool
    actions_required: Tuple[str, ...] = ()
    actions_completed: Tuple[str, ...] = ()
    passive_score: float = 1.0
    frames: int = 0
    #: True only when the report comes from a multi-frame capture in which the
    #: person actually performed a challenge.  A single photo can never set it.
    live_evidence: bool = False
    reasons: Tuple[str, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        return self.passed

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "required": list(self.actions_required),
            "completed": list(self.actions_completed),
            "passive_score": round(self.passive_score, 3),
            "frames": self.frames,
            "live_evidence": self.live_evidence,
            "reasons": list(self.reasons),
        }

    def explain(self) -> str:
        if self.passed:
            done = ", ".join(self.actions_completed) or "no actions needed"
            return f"Live person confirmed ({done}; anti-spoof score {self.passive_score:.2f})."
        return "Liveness failed: " + ("; ".join(self.reasons) or "actions not completed")


# --------------------------------------------------------------------------- #
# Passive heuristics
# --------------------------------------------------------------------------- #
def passive_check(image, *, threshold: float = 0.45) -> Tuple[float, Tuple[str, ...]]:
    """Score how likely an image is a *real* face versus a re-photographed screen.

    Returns ``(score, reasons)`` where ``score`` is 0 (almost certainly a
    replay) … 1 (nothing suspicious).
    """
    import cv2

    pixels = load_image(image)
    gray = cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY)
    reasons: List[str] = []
    score = 1.0

    # 1. High-frequency detail -------------------------------------------------
    laplacian = cv2.Laplacian(gray, cv2.CV_64F).var()
    if laplacian < 8.0:
        score -= 0.45
        reasons.append("image is very soft (possible printed photo or screen)")

    # 2. Moiré: a strong periodic peak in the frequency spectrum ---------------
    size = 256
    resized = cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)
    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(resized.astype(np.float32))))
    spectrum[size // 2 - 3: size // 2 + 3, size // 2 - 3: size // 2 + 3] = 0  # drop DC
    total = float(spectrum.sum()) + 1e-9
    peak = float(np.percentile(spectrum, 99.98))
    if peak / total > 0.012:
        score -= 0.25
        reasons.append("periodic screen pattern detected (moiré)")

    # 3. Blown-out specular highlights ----------------------------------------
    hsv = cv2.cvtColor(pixels, cv2.COLOR_BGR2HSV)
    bright = (hsv[:, :, 2] > 248).mean()
    low_sat = (hsv[:, :, 1] < 12).mean()
    if bright > 0.02 and low_sat > 0.15:
        score -= 0.20
        reasons.append("large flat reflections (possible screen glare)")

    # 4. Colour richness — printed paper is often duller than a live face ------
    colourfulness = float(np.std(pixels[:, :, 1].astype(np.float32) - pixels[:, :, 2]))
    if colourfulness < 1.2:
        score -= 0.10
        reasons.append("very low colour variation")

    score = float(np.clip(score, 0.0, 1.0))
    if score < threshold and not reasons:  # pragma: no cover - defensive
        reasons.append("anti-spoof score too low")
    return score, tuple(reasons)


# --------------------------------------------------------------------------- #
# Active challenge tracking
# --------------------------------------------------------------------------- #
def random_actions(
    count: int = 2, pool: Optional[Sequence[str]] = None
) -> Tuple[str, ...]:
    """Pick ``count`` distinct random challenges (any pool by default)."""
    choices = list(pool) if pool else list(_DEFAULT_POOL)
    count = max(0, min(int(count), len(choices)))
    return tuple(random.sample(choices, count))


class LivenessTracker:
    """Track a person's head across frames until every challenge is satisfied."""

    def __init__(self, actions: Sequence[str], *, frame_budget: int = 90) -> None:
        self.actions = tuple(actions)
        self.completed: List[str] = []
        self.frame_budget = frame_budget
        self.frames = 0
        self.start_width: Optional[float] = None
        self.baseline_pitch: Optional[float] = None
        self._eye_cascade = None
        self._blink_state = "open"
        self._blinks = 0
        self._turn_sign: Optional[int] = None

    # -- helpers ---------------------------------------------------------- #
    @property
    def pending(self) -> List[str]:
        return [a for a in self.actions if a not in self.completed]

    @property
    def current(self) -> Optional[str]:
        return self.pending[0] if self.pending else None

    @property
    def prompt(self) -> str:
        action = self.current
        if action is None:
            return "Thank you — hold still"
        if action in {"turn_left", "turn_right"} and self._turn_sign is not None:
            return "Now turn your head the other way"
        return ACTIONS.get(action, action)

    @property
    def progress(self) -> float:
        return len(self.completed) / max(len(self.actions), 1)

    def _pitch(self, landmarks: np.ndarray) -> float:
        right_eye, left_eye, nose, right_mouth, left_mouth = np.asarray(landmarks, np.float64)
        eye_mid = (right_eye + left_eye) / 2.0
        mouth_mid = (right_mouth + left_mouth) / 2.0
        span = max(abs(mouth_mid[1] - eye_mid[1]), 1e-6)
        return float((nose[1] - eye_mid[1]) / span)

    def _eyes_visible(self, frame: np.ndarray, face: DetectedFace) -> bool:
        """Very cheap blink proxy using OpenCV's bundled Haar eye cascade."""
        import cv2

        if self._eye_cascade is None:
            try:
                path = cv2.data.haarcascades + "haarcascade_eye.xml"
                self._eye_cascade = cv2.CascadeClassifier(path)
            except Exception:  # pragma: no cover
                self._eye_cascade = False
        if self._eye_cascade is False:
            return True
        x, y, w, h = face.box
        y0 = max(0, int(y))
        y1 = min(frame.shape[0], int(y + h * 0.62))
        x0 = max(0, int(x))
        x1 = min(frame.shape[1], int(x + w))
        if y1 - y0 < 24 or x1 - x0 < 24:
            return True
        region = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        try:
            eyes = self._eye_cascade.detectMultiScale(region, 1.15, 4, minSize=(12, 12))
        except Exception:  # pragma: no cover
            return True
        return len(eyes) >= 1

    # -- main loop ---------------------------------------------------------- #
    def update(self, frame: np.ndarray, face: DetectedFace) -> List[str]:
        """Feed one frame; returns the actions completed by this frame."""
        self.frames += 1
        newly: List[str] = []
        yaw, _roll = _estimate_pose(face.landmarks)
        pitch = self._pitch(face.landmarks)

        if self.start_width is None:
            self.start_width = max(face.width, 1e-6)
        if self.baseline_pitch is None:
            self.baseline_pitch = pitch

        action = self.current
        if action is None:
            return newly

        done = False
        if action in {"turn_left", "turn_right"}:
            # Mirror-safe: the first turn accepts either direction, a second turn
            # challenge then requires the opposite direction.
            if abs(yaw) >= 16.0:
                sign = 1 if yaw > 0 else -1
                if self._turn_sign is None:
                    self._turn_sign = sign
                    done = True
                elif sign != self._turn_sign:
                    self._turn_sign = sign
                    done = True
        elif action == "nod":
            if abs(pitch - (self.baseline_pitch or pitch)) >= 0.10:
                done = True
                self.baseline_pitch = pitch
        elif action == "come_closer":
            if face.width >= (self.start_width or face.width) * 1.12:
                done = True
        elif action == "blink":
            visible = self._eyes_visible(frame, face)
            if self._blink_state == "open" and not visible:
                self._blink_state = "closed"
            elif self._blink_state == "closed" and visible:
                self._blink_state = "open"
                self._blinks += 1
                if self._blinks >= 2:
                    done = True

        if done:
            self.completed.append(action)
            newly.append(action)
        return newly

    def report(
        self,
        *,
        passive_score: float = 1.0,
        reasons: Sequence[str] = (),
        live_evidence: Optional[bool] = None,
    ) -> LivenessReport:
        passed = not self.pending
        extra = list(reasons)
        if not passed:
            extra.append("challenges not completed: " + ", ".join(self.pending))
        if live_evidence is None:
            # multi-frame capture with every challenge completed is the only
            # thing this library accepts as proof that a person was present
            live_evidence = passed and self.frames > 1
        return LivenessReport(
            passed=passed,
            actions_required=self.actions,
            actions_completed=tuple(self.completed),
            passive_score=float(passive_score),
            frames=self.frames,
            live_evidence=bool(live_evidence),
            reasons=tuple(extra),
        )


# --------------------------------------------------------------------------- #
# One-shot convenience
# --------------------------------------------------------------------------- #
def check(image, *, threshold: float = 0.45) -> LivenessReport:
    """Passive-only liveness check on a single photo (no challenges).

    Useful for uploads, where you cannot ask the person to move.  Clearly
    weaker than a live scan — treat it as a filter, not a guarantee.
    """
    score, reasons = passive_check(image, threshold=threshold)
    return LivenessReport(
        passed=score >= threshold,
        actions_required=(),
        actions_completed=(),
        passive_score=score,
        frames=1,
        reasons=tuple(reasons),
    )


__all__ = [
    "ACTIONS",
    "LivenessReport",
    "LivenessTracker",
    "passive_check",
    "random_actions",
    "check",
]
