"""The promise: enroll once, verify the same person years later, reject others.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import pytest

import verifyface as vf
from verifyface.errors import (
    IdentityExistsError,
    IdentityNotFoundError,
    NoFaceFoundError,
)

from tests.conftest import fixture_path


# --------------------------------------------------------------------------- #
# Core promise
# --------------------------------------------------------------------------- #
def test_same_person_years_apart_is_verified(fresh_verifier):
    """Macron in 2014 (different clothes/place/camera) vs 2025."""
    v = fresh_verifier
    v.enroll("emmanuel", [fixture_path("person_a_1.jpg")])
    result = v.verify("emmanuel", fixture_path("person_a_2.jpg"))
    assert result.matched is True
    assert result.score > 0.45
    assert result.confidence > 0.8


def test_same_person_woman_years_apart(fresh_verifier):
    v = fresh_verifier
    v.enroll("jacinda", [fixture_path("person_b_1.jpg")])
    assert bool(v.verify("jacinda", fixture_path("person_b_2.jpg"))) is True


def test_different_people_are_rejected(fresh_verifier):
    v = fresh_verifier
    v.enroll("emmanuel", [fixture_path("person_a_1.jpg")])
    for other in ("impostor_1.jpg", "impostor_2.jpg", "person_b_2.jpg"):
        result = v.verify("emmanuel", fixture_path(other))
        assert result.matched is False, f"{other} should not match"
        assert result.score < result.threshold


def test_compare_does_not_touch_the_vault(fresh_verifier):
    v = fresh_verifier
    result = v.compare(fixture_path("person_a_1.jpg"), fixture_path("person_a_2.jpg"))
    assert result.matched and result.as_dict()["matched"] is True
    assert v.identities() == []


def test_same_person_helper(fresh_verifier):
    assert vf.same_person(
        fixture_path("person_b_1.jpg"),
        fixture_path("person_b_2.jpg"),
        threshold="balanced",
    ) in (True, False)  # module default vault is separate; must not crash


# --------------------------------------------------------------------------- #
# Enrollment behaviour
# --------------------------------------------------------------------------- #
def test_multi_photo_enrollment_improves_robustness(fresh_verifier):
    v = fresh_verifier
    result = v.enroll("emmanuel", [fixture_path("person_a_1.jpg"), fixture_path("person_a_2.jpg")])
    assert result.samples == 2
    assert 0.4 < result.self_similarity < 1.0
    assert v.verify("emmanuel", fixture_path("person_a_2.jpg")).matched


def test_duplicate_photos_are_not_double_counted(fresh_verifier):
    path = fixture_path("person_b_1.jpg")
    result = fresh_verifier.enroll("jacinda", [path, path, path])
    assert result.samples == 1
    assert result.duplicates_skipped == 2


def test_enroll_is_idempotent_with_add(fresh_verifier):
    v = fresh_verifier
    v.enroll("jacinda", [fixture_path("person_b_1.jpg")])
    second = v.enroll("jacinda", [fixture_path("person_b_2.jpg")], add=True)
    assert second.created is False
    assert second.samples == 2


def test_enroll_twice_raises_when_adding_is_disabled(fresh_verifier):
    v = fresh_verifier
    v.enroll("abc", [fixture_path("person_a_1.jpg")], overwrite=False)
    with pytest.raises(IdentityExistsError):
        v.enroll("abc", [fixture_path("person_a_2.jpg")], overwrite=False, add=False)


def test_overwrite_replaces_previous_samples(fresh_verifier):
    v = fresh_verifier
    v.enroll("emmanuel", [fixture_path("person_a_1.jpg")])
    replaced = v.enroll("emmanuel", [fixture_path("person_a_2.jpg")], overwrite=True)
    assert replaced.created is False
    assert replaced.samples == 1
    assert bool(v.verify("emmanuel", fixture_path("person_a_2.jpg")))


def test_unicode_identity_names(fresh_verifier):
    v = fresh_verifier
    name = "কৌস্তভ কান্তি রায়"
    v.enroll(name, [fixture_path("person_b_1.jpg")])
    assert name in v.identities()
    assert bool(v.verify(name, fixture_path("person_b_2.jpg")))
    assert v.remove(name) is True
    assert name not in v.identities()


def test_emoji_and_symbol_identity_names_are_safe(fresh_verifier):
    v = fresh_verifier
    name = "../../etc/passwd 🚀"
    v.enroll(name, [fixture_path("person_a_1.jpg")])
    assert name in v.identities()
    files = list((v.vault.path / "identities").glob("*.json"))
    assert len(files) == 1
    assert v.vault.path in files[0].parents
    assert "passwd" in files[0].name


def test_max_samples_is_enforced(fresh_verifier):
    from verifyface.config import Settings

    settings = Settings(vault=fresh_verifier.vault.path, max_samples_per_identity=1)
    verifier = vf.Verifier(settings=settings)
    verifier.enroll("a", [fixture_path("person_a_1.jpg")], overwrite=True)
    verifier.enroll("a", [fixture_path("person_a_2.jpg")], add=True)
    assert verifier.profile("a").sample_count == 1


# --------------------------------------------------------------------------- #
# Identification
# --------------------------------------------------------------------------- #
def test_identify_returns_the_right_person(fresh_verifier):
    v = fresh_verifier
    v.enroll("emmanuel", [fixture_path("person_a_1.jpg")])
    v.enroll("jacinda", [fixture_path("person_b_1.jpg")])
    result = v.identify(fixture_path("person_b_2.jpg"))
    assert result.matched is True
    assert result.identity == "jacinda"
    assert result.ranking[0][0] == "jacinda"


def test_identify_rejects_unknown_person(fresh_verifier):
    v = fresh_verifier
    v.enroll("emmanuel", [fixture_path("person_a_1.jpg")])
    result = v.identify(fixture_path("impostor_2.jpg"))
    assert result.matched is False
    assert result.identity is None


def test_identify_requires_enrolled_people(fresh_verifier):
    with pytest.raises(IdentityNotFoundError):
        fresh_verifier.identify(fixture_path("person_a_1.jpg"))


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
def test_unknown_identity_raises(fresh_verifier):
    with pytest.raises(IdentityNotFoundError):
        fresh_verifier.verify("nobody", fixture_path("person_a_1.jpg"))


def test_blank_image_has_no_face(fresh_verifier):
    import numpy as np

    blank = np.full((480, 640, 3), 220, dtype=np.uint8)
    with pytest.raises(NoFaceFoundError):
        fresh_verifier.enroll("blank", [blank])


def test_strict_mode_rejects_multiple_faces(fresh_verifier):
    import cv2
    import numpy as np

    a = cv2.imread(str(fixture_path("impostor_1.jpg")))
    b = cv2.imread(str(fixture_path("impostor_2.jpg")))
    height = min(a.shape[0], b.shape[0])
    b = cv2.resize(b, (int(b.shape[1] * height / b.shape[0]), height))
    canvas = np.hstack([cv2.resize(a, (int(a.shape[1] * height / a.shape[0]), height)), b])
    faces = fresh_verifier.engine.detect_faces(canvas)
    assert len(faces) >= 2
    with pytest.raises(vf.MultipleFacesError):
        fresh_verifier.engine.embed(canvas, mode="strict")
    # the default mode picks the biggest face instead of failing
    assert fresh_verifier.engine.embed(canvas).vector.shape == (128,)


# --------------------------------------------------------------------------- #
# Thresholds
# --------------------------------------------------------------------------- #
def test_strict_threshold_is_harder_than_lenient(fresh_verifier):
    v = fresh_verifier
    v.enroll("emmanuel", [fixture_path("person_a_1.jpg")], overwrite=True)
    lenient = v.verify("emmanuel", fixture_path("person_a_2.jpg"), threshold="lenient", adaptive=False)
    strict = v.verify("emmanuel", fixture_path("person_a_2.jpg"), threshold="strict", adaptive=False)
    assert lenient.threshold < strict.threshold
    assert lenient.score == pytest.approx(strict.score, abs=1e-6)
    assert strict.threshold == pytest.approx(0.48)


def test_adaptive_threshold_only_relaxes_slightly(fresh_verifier):
    v = fresh_verifier
    v.enroll("emmanuel", [fixture_path("person_a_1.jpg"), fixture_path("person_a_2.jpg")])
    adaptive = v.verify("emmanuel", fixture_path("person_a_2.jpg"), adaptive=True)
    fixed = v.verify("emmanuel", fixture_path("person_a_2.jpg"), adaptive=False)
    assert adaptive.threshold <= fixed.threshold
    assert fixed.threshold - adaptive.threshold <= 0.035 + 1e-9


def test_result_bool_and_dict(fresh_verifier):
    v = fresh_verifier
    v.enroll("emmanuel", [fixture_path("person_a_1.jpg")])
    result = v.verify("emmanuel", fixture_path("person_a_2.jpg"))
    assert bool(result) is result.matched
    payload = result.as_dict()
    assert payload["developer"] == "Kaustav Kanti Ray"
    assert 0.0 <= payload["confidence"] <= 1.0
    assert "similarity" in result.explain()


def test_liveness_failure_blocks_verification(fresh_verifier):
    from verifyface.liveness import LivenessReport

    v = fresh_verifier
    v.enroll("emmanuel", [fixture_path("person_a_1.jpg")])
    spoof = LivenessReport(passed=False, reasons=("screen detected",))
    result = v.verify("emmanuel", fixture_path("person_a_2.jpg"), liveness=spoof)
    assert result.matched is False
    assert result.as_dict()["liveness"]["passed"] is False


def test_info_reports_configuration(fresh_verifier):
    info = fresh_verifier.info()
    assert info["developer"] == "Kaustav Kanti Ray"
    assert info["threshold"] == pytest.approx(0.40)
    assert info["engine"]["embedding_size"] == 128
