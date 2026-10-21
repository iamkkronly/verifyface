"""Liveness: challenges must be satisfied by geometry, not by a still photo.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import numpy as np
import pytest

from verifyface.imageio import load_image
from verifyface.liveness import (
    LivenessTracker,
    passive_check,
    random_actions,
)
from verifyface.preprocess import DetectedFace

from tests.conftest import fixture_path


def _face(yaw_offset: float = 0.0, width: float = 120.0, pitch: float = 0.5) -> DetectedFace:
    """Build a synthetic face with a controllable yaw/pitch/scale."""
    eye_span = 60.0
    right_eye_x = 100.0 - yaw_offset * 6.0
    left_eye_x = right_eye_x + eye_span
    nose_x = (right_eye_x + left_eye_x) / 2 + yaw_offset * eye_span * 0.5
    eye_y = 100.0
    mouth_y = eye_y + 60.0
    landmarks = np.array(
        [
            [right_eye_x, eye_y],
            [left_eye_x, eye_y],
            [nose_x, eye_y + pitch * 60.0],
            [right_eye_x + 6, mouth_y],
            [left_eye_x - 6, mouth_y],
        ],
        dtype=np.float32,
    )
    return DetectedFace(
        box=(min(right_eye_x, left_eye_x) - 30, eye_y - 40, width, width * 1.3),
        landmarks=landmarks,
        score=0.99,
    )


def test_random_actions_are_distinct():
    actions = random_actions(3)
    assert len(actions) == 3
    assert len(set(actions)) == 3


def test_passive_check_on_real_photos():
    for name in ("person_a_2.jpg", "person_b_2.jpg", "impostor_1.jpg"):
        score, reasons = passive_check(fixture_path(name))
        assert 0.0 <= score <= 1.0
        assert score >= 0.35, f"{name} flagged as spoof: {reasons}"


def test_passive_check_rejects_flat_noise():
    """A featureless grey card is not a live face."""
    flat = np.full((480, 640, 3), 128, dtype=np.uint8)
    score, reasons = passive_check(flat)
    assert score < 0.9
    assert reasons


def test_turn_left_challenge_completes():
    tracker = LivenessTracker(["turn_left"])
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    tracker.update(frame, _face(0.0))
    assert tracker.pending == ["turn_left"]
    tracker.update(frame, _face(-1.0))       # nose moves to the subject's right
    assert tracker.completed == ["turn_left"]
    assert tracker.report().passed is True


def test_still_face_never_completes_a_challenge():
    tracker = LivenessTracker(["turn_left"])
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for _ in range(30):
        tracker.update(frame, _face(0.0))    # exactly the same still photo
    assert tracker.pending == ["turn_left"]
    assert tracker.report().passed is False


def test_come_closer_challenge():
    tracker = LivenessTracker(["come_closer"])
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    tracker.update(frame, _face(width=120))
    tracker.update(frame, _face(width=150))   # 25 % larger
    assert "come_closer" in tracker.completed


def test_nod_challenge():
    tracker = LivenessTracker(["nod"])
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    tracker.update(frame, _face(pitch=0.5))
    tracker.update(frame, _face(pitch=0.65))
    assert "nod" in tracker.completed


def test_report_explains_failure():
    tracker = LivenessTracker(["turn_right", "nod"])
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    tracker.update(frame, _face())
    report = tracker.report(passive_score=0.9)
    assert report.passed is False
    assert "challenges not completed" in report.explain()
    assert report.as_dict()["required"] == ["turn_right", "nod"]


# --------------------------------------------------------------------------- #
# LiveSession (the piece web apps use)
# --------------------------------------------------------------------------- #
def test_live_session_verifies_without_challenges(fresh_verifier):
    from verifyface.camera import LiveSession

    fresh_verifier.enroll("emmanuel", [fixture_path("person_a_1.jpg")])
    session = LiveSession(identity="emmanuel", verifier=fresh_verifier, actions=0)
    assert session.begin()["status"] == "prompt"
    state = session.feed(fixture_path("person_a_2.jpg"))
    assert state["status"] == "done"
    assert state["passed"] is True
    assert session.result.verify.matched is True
    assert session.preview_data_uri().startswith("data:image/jpeg;base64,")


def test_live_session_rejects_impostor(fresh_verifier):
    from verifyface.camera import LiveSession

    fresh_verifier.enroll("emmanuel", [fixture_path("person_a_1.jpg")])
    session = LiveSession(identity="emmanuel", verifier=fresh_verifier, actions=0)
    session.begin()
    state = session.feed(fixture_path("impostor_2.jpg"))
    assert state["status"] == "done"
    assert state["passed"] is False


def test_live_session_prompts_for_missing_face(fresh_verifier):
    from verifyface.camera import LiveSession

    fresh_verifier.enroll("emmanuel", [fixture_path("person_a_1.jpg")])
    session = LiveSession(identity="emmanuel", verifier=fresh_verifier, actions=0)
    session.begin()
    blank = np.full((360, 480, 3), 240, dtype=np.uint8)
    state = session.feed(blank)
    assert state["status"] == "prompt"
    assert "No face" in state["prompt"]


def test_live_session_enroll_mode(fresh_verifier):
    from verifyface.camera import LiveSession

    session = LiveSession(identity="new-person", verifier=fresh_verifier, mode="enroll", actions=0)
    session.begin()
    state = session.feed(fixture_path("person_b_1.jpg"))
    assert state["status"] == "done"
    assert "new-person" in fresh_verifier.identities()


def test_live_session_requires_identity_in_verify_mode(fresh_verifier):
    from verifyface.camera import LiveSession

    with pytest.raises(ValueError):
        LiveSession(verifier=fresh_verifier, mode="verify")


def test_live_session_challenge_prompt_is_human(fresh_verifier):
    from verifyface.camera import LiveSession

    fresh_verifier.enroll("emmanuel", [fixture_path("person_a_1.jpg")])
    session = LiveSession(identity="emmanuel", verifier=fresh_verifier, actions=1)
    state = session.begin()
    assert state["actions_required"]
    assert isinstance(state["prompt"], str) and len(state["prompt"]) > 5
    # the same still frame must not satisfy a movement challenge
    for _ in range(5):
        state = session.feed(fixture_path("person_a_2.jpg"))
    assert state["status"] == "prompt"
    assert state["passed"] is False
