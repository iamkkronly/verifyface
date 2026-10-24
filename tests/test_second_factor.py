"""Second factor: a PIN makes twins/lookalikes separable.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import json

import pytest

from tests.conftest import fixture_path
from verifyface.errors import (
    ConfigError,
    IdentityNotFoundError,
    TemplateCorruptedError,
)
from verifyface.security import hash_pin, verify_pin

A1 = "person_a_1.jpg"
A2 = "person_a_2.jpg"


# --------------------------------------------------------------------------- #
# Hashing primitives
# --------------------------------------------------------------------------- #
def test_pin_hash_roundtrip():
    record = hash_pin("correct horse")
    assert record.startswith("scrypt$")
    assert verify_pin("correct horse", record) is True
    assert verify_pin("wrong horse", record) is False


def test_pin_hash_is_salted():
    assert hash_pin("1234") != hash_pin("1234")


def test_pin_hash_survives_a_damaged_record():
    assert verify_pin("1234", "garbage") is False
    assert verify_pin("1234", "") is False
    assert verify_pin("1234", "md5$1$2$3$4$5") is False


@pytest.mark.parametrize("bad", ["", "  ", "123"])
def test_short_pins_are_rejected(bad):
    with pytest.raises(ConfigError):
        hash_pin(bad)


# --------------------------------------------------------------------------- #
# Verifier API
# --------------------------------------------------------------------------- #
def test_set_and_clear_pin(fresh_verifier):
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    assert v.has_pin("a") is False

    v.set_pin("a", "1234")
    assert v.has_pin("a") is True
    assert v.check_pin("a", "1234") is True
    assert v.check_pin("a", "0000") is False
    assert v.check_pin("a", None) is False

    v.clear_pin("a")
    assert v.has_pin("a") is False


def test_pin_is_required_for_verification(fresh_verifier):
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    v.set_pin("a", "1234")

    missing = v.verify("a", fixture_path(A2))
    assert missing.matched is False
    assert missing.requires_second_factor is True
    assert missing.second_factor_ok is False

    wrong = v.verify("a", fixture_path(A2), pin="0000")
    assert wrong.matched is False

    right = v.verify("a", fixture_path(A2), pin="1234")
    assert right.matched is True
    assert right.second_factor_ok is True


def test_pin_survives_re_enrollment(fresh_verifier):
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    v.set_pin("a", "1234")
    v.enroll("a", [fixture_path(A2)], overwrite=True)     # replace the face samples
    assert v.has_pin("a") is True
    assert v.verify("a", fixture_path(A1), pin="1234").matched is True


def test_pin_never_leaks_into_the_plain_template(fresh_verifier):
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    v.set_pin("a", "9876")
    raw = next(
        p for p in (v.vault.path / "identities").glob("*.json") if not p.name.endswith(".bak")
    ).read_text(encoding="utf-8")
    assert "9876" not in raw, "the PIN must never be stored in clear text"
    payload = json.loads(raw)
    assert payload["algorithm"] in {"aes-256-gcm", "hmac-sha256"}


def test_pin_for_unknown_identity(fresh_verifier):
    with pytest.raises(IdentityNotFoundError):
        fresh_verifier.set_pin("ghost", "1234")
    assert fresh_verifier.check_pin("ghost", "1234") is False


def test_damaged_pin_record_cannot_be_used_to_bypass(fresh_verifier):
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    v.set_pin("a", "1234")
    payload = v.vault.load_payload("a")
    payload["pin"] = "scrypt$16384$8$1$AAAA$AAAA"
    from verifyface.security import seal

    envelope = seal(v.vault.key, payload)
    live = next(
        p for p in (v.vault.path / "identities").glob("*.json") if not p.name.endswith(".bak")
    )
    live.write_text(json.dumps(envelope), encoding="utf-8")
    assert v.check_pin("a", "1234") is False


def test_setting_a_pin_keeps_the_face_samples(fresh_verifier):
    v = fresh_verifier
    result = v.enroll("a", [fixture_path(A1), fixture_path(A2)])
    before = v.profile("a").sample_count
    v.set_pin("a", "1234")
    after = v.profile("a")
    assert after.sample_count == before == result.samples
    assert after.centroid.shape == (128,)


def test_twin_scenario_is_solved_by_a_pin(fresh_verifier):
    """The reported failure: two twins, one enrolled identity each."""
    v = fresh_verifier
    v.enroll("twin_1", [fixture_path(A1)])
    v.enroll("twin_2", [fixture_path(A1)])   # the same face: the hardest case
    assert v.lookalikes(), "twins should be reported as a lookalike pair"

    v.set_pin("twin_1", "1111")
    v.set_pin("twin_2", "2222")

    # the face alone can no longer let either twin in
    assert v.verify("twin_1", fixture_path(A2)).matched is False
    assert v.verify("twin_2", fixture_path(A1)).matched is False

    # face + the correct PIN does
    assert v.verify("twin_1", fixture_path(A2), pin="1111").matched is True
    # and the other twin's PIN is not a substitute
    assert v.verify("twin_1", fixture_path(A2), pin="2222").matched is False


def test_identify_cannot_bypass_a_pin(fresh_verifier):
    """1:N search used to hand out a PIN-protected identity with no PIN at all."""
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    v.enroll("b", [fixture_path("person_b_1.jpg")])
    v.set_pin("a", "1234")

    blocked = v.identify(fixture_path(A2))
    assert blocked.matched is False
    assert blocked.requires_second_factor is True
    assert blocked.second_factor_ok is False
    assert blocked.as_dict()["reasons"]
    assert "PIN" in blocked.explain() and "<" not in blocked.explain()

    assert v.identify(fixture_path(A2), pin="0000").matched is False
    allowed = v.identify(fixture_path(A2), pin="1234")
    assert allowed.matched is True
    assert allowed.identity == "a"

    # an identity without a PIN is unaffected
    assert v.identify(fixture_path("person_b_2.jpg")).identity == "b"


def test_corrupted_template_still_raises(fresh_verifier):
    v = fresh_verifier
    v.enroll("a", [fixture_path(A1)])
    v.set_pin("a", "1234")
    for path in (v.vault.path / "identities").glob("*.json*"):
        path.write_text("garbage", encoding="utf-8")
    with pytest.raises(TemplateCorruptedError):
        v.verify("a", fixture_path(A2), pin="1234")
