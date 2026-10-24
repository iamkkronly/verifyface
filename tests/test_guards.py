"""The security guards added in 1.1.0, each one matching a reported failure.

* identical twins / siblings  → ambiguity guard + second factor
* a photo of a photo          → passive liveness inside verify()
* re-using an enrolled file   → replay detection
* a lazy enrollment photo     → robust identity centroid

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import numpy as np
import pytest

import verifyface as vf
from tests.conftest import fixture_path
from verifyface.errors import ConfigError
from verifyface.store import robust_centroid

A1 = "person_a_1.jpg"
A2 = "person_a_2.jpg"
B1 = "person_b_1.jpg"


# --------------------------------------------------------------------------- #
# Twins / lookalikes
# --------------------------------------------------------------------------- #
def test_lookalike_identity_blocks_verification(fresh_verifier):
    """Enrolling a near-identical identity must stop a silent false accept.

    This reproduces the reported twin failure without using a real twin: the
    same face is enrolled twice under two names, which is the situation the
    library previously accepted blindly.
    """
    v = fresh_verifier
    v.enroll("person_a", [fixture_path(A1)])
    v.enroll("person_a_lookalike", [fixture_path(A2)])

    result = v.verify("person_a", fixture_path(A2))
    assert result.score >= result.threshold, "similarity itself is high, as reported"
    assert result.ambiguous is True
    assert result.matched is False, "a lookalike in the gallery must not pass silently"
    assert result.second_best is not None
    assert result.second_best[0] == "person_a_lookalike"
    assert "second factor" in result.explain()


def test_ambiguity_guard_can_be_disabled_per_call(fresh_verifier):
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    v.enroll("b", [fixture_path(A1)])
    result = v.verify("a", fixture_path(A2), ambiguity_guard=False)
    assert result.ambiguous is True
    assert result.matched is True


def test_no_ambiguity_when_gallery_has_one_person(fresh_verifier):
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    result = v.verify("a", fixture_path(A2))
    assert result.ambiguous is False
    assert result.matched is True


def test_unrelated_second_person_does_not_block(fresh_verifier):
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    v.enroll("b", [fixture_path(B1)])
    result = v.verify("a", fixture_path(A2))
    assert result.ambiguous is False
    assert result.matched is True


def test_lookalikes_report(fresh_verifier):
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    v.enroll("b", [fixture_path(B1)])
    assert v.lookalikes() == []
    v.enroll("a2", [fixture_path(A1)])
    pairs = v.lookalikes()
    assert len(pairs) == 1
    names = {pairs[0][0], pairs[0][1]}
    assert names == {"a", "a2"}
    assert pairs[0][2] > 0.5


def test_identify_reports_ambiguity(fresh_verifier):
    """Two identities built from the same face score equally — like twins do."""
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    v.enroll("a2", [fixture_path(A1)])
    result = v.identify(fixture_path(A2))
    assert result.ambiguous is True, result.ranking
    assert result.margin < v.ambiguity_margin
    assert result.matched is False
    assert "Ambiguous" in result.explain()


# --------------------------------------------------------------------------- #
# Replay of an enrolled file
# --------------------------------------------------------------------------- #
def test_exact_replay_of_enrolled_file_is_flagged(fresh_verifier):
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    warned = v.verify("a", fixture_path(A1))
    assert warned.replayed_sample is True
    assert any("exact image" in reason for reason in warned.reasons)

    # standard profile only warns; high-security refuses outright
    blocked = v.verify("a", fixture_path(A1), block_replay=True)
    assert blocked.matched is False


def test_replay_detection_can_be_skipped(fresh_verifier):
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    result = v.verify("a", fixture_path(A1), check_replay=False)
    assert result.replayed_sample is False
    assert result.matched is True


def test_replay_detection_is_off_without_hashes(fresh_verifier):
    from verifyface.config import Settings

    settings = Settings(store_source_hashes=False, vault=fresh_verifier.vault.path)
    verifier = vf.Verifier(settings=settings)
    verifier.enroll("a", [fixture_path(A1)], overwrite=True)
    assert verifier.profile("a").source_hashes == ()
    assert verifier.verify("a", fixture_path(A1)).replayed_sample is False


# --------------------------------------------------------------------------- #
# Liveness inside verify()
# --------------------------------------------------------------------------- #
def test_liveness_auto_passes_a_real_photo(fresh_verifier):
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    result = v.verify("a", fixture_path(A2), liveness="auto")
    assert result.liveness_status == "passed"
    assert result.matched is True


def test_liveness_auto_rejects_a_flat_fake(fresh_verifier):
    """A featureless card is refused, and the reason is reported."""
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    with pytest.raises(vf.NoFaceFoundError):
        # a blank image has no face at all — that path is covered elsewhere;
        # here we only assert that liveness cannot turn it into a pass
        v.verify("a", np.full((480, 640, 3), 128, np.uint8), liveness="auto")


def test_require_liveness_setting(fresh_verifier):
    from verifyface.config import Settings

    settings = Settings(vault=fresh_verifier.vault.path)
    verifier = vf.Verifier(settings=settings, require_liveness=True)
    verifier.enroll("a", [fixture_path(A1)], overwrite=True)
    result = verifier.verify("a", fixture_path(A2))
    assert result.liveness_status == "passed"


def test_liveness_required_raises_on_failure(fresh_verifier, monkeypatch):
    """When the caller demands liveness, a spoof raises instead of returning False."""
    import verifyface.liveness as liveness_module

    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])

    monkeypatch.setattr(
        liveness_module,
        "check",
        lambda *a, **k: liveness_module.LivenessReport(
            passed=False, passive_score=0.1, reasons=("screen detected",)
        ),
    )
    with pytest.raises(vf.LivenessCheckFailed):
        v.verify("a", fixture_path(A2), liveness="required")


# --------------------------------------------------------------------------- #
# Profiles
# --------------------------------------------------------------------------- #
def test_profiles_bundle_the_right_knobs():
    from verifyface.config import Settings

    settings = Settings(vault="/tmp/vf-profile-test")
    strict = vf.Verifier(settings=settings, profile="high_security")
    assert strict.threshold == pytest.approx(0.48)
    assert strict.require_liveness is True
    assert strict.ambiguity_guard is True

    relaxed = vf.Verifier(settings=settings, profile="convenience")
    assert relaxed.threshold == pytest.approx(0.33)
    assert relaxed.require_liveness is False
    assert relaxed.ambiguity_guard is False


def test_unknown_profile_is_rejected():
    with pytest.raises(ConfigError):
        vf.Verifier(profile="ultimate")


def test_info_reports_the_security_posture(fresh_verifier):
    info = fresh_verifier.info()
    assert info["profile"] == "standard"
    assert info["ambiguity_guard"] is True
    assert 0 < info["ambiguity_margin"] < 1


# --------------------------------------------------------------------------- #
# Robust centroid
# --------------------------------------------------------------------------- #
def test_robust_centroid_resists_one_bad_photo():
    good_a = np.array([1.0, 0.05, 0.0], dtype=np.float32)
    good_b = np.array([0.98, 0.10, 0.02], dtype=np.float32)
    good_c = np.array([0.99, 0.02, 0.05], dtype=np.float32)
    bad = np.array([0.0, 1.0, 0.0], dtype=np.float32)   # eyes closed / stranger
    matrix = np.stack([good_a, good_b, good_c, bad])
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)

    robust = robust_centroid(matrix)
    plain = matrix.mean(axis=0)
    plain /= np.linalg.norm(plain)

    reference = (good_a + good_b + good_c) / 3.0
    reference /= np.linalg.norm(reference)
    assert float(robust @ reference) > float(plain @ reference)


def test_robust_centroid_single_and_double():
    one = np.array([[0.0, 1.0, 0.0]], dtype=np.float32)
    assert np.allclose(robust_centroid(one), [0.0, 1.0, 0.0])
    two = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    assert np.allclose(np.linalg.norm(robust_centroid(two)), 1.0)
