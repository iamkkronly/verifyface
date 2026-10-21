"""A template must never be corrupt or silently wrong.

These tests damage templates on purpose and check that verifyface notices,
recovers, or refuses — never that it quietly verifies the wrong person.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import json
import os

import numpy as np
import pytest

import verifyface as vf
from verifyface.errors import TemplateCorruptedError
from verifyface.security import fingerprint, load_or_create_key, seal, unseal
from verifyface.store import slugify

from tests.conftest import fixture_path


def _enroll(fresh_verifier, name: str = "tester"):
    fresh_verifier.enroll(name, [fixture_path("person_a_1.jpg")], overwrite=True)
    return fresh_verifier


def _template_path(verifier, name: str):
    files = [p for p in (verifier.vault.path / "identities").glob("*.json")
             if not p.name.endswith(".bak")]
    assert len(files) == 1
    return files[0]


# --------------------------------------------------------------------------- #
# Keys and envelopes
# --------------------------------------------------------------------------- #
def test_key_is_created_private(tmp_path):
    key = load_or_create_key(tmp_path)
    assert len(key) == 32
    key_file = tmp_path / "key.bin"
    assert key_file.is_file()
    if os.name != "nt":
        mode = key_file.stat().st_mode & 0o777
        assert mode == 0o600, f"key permissions are {oct(mode)}"


def test_key_is_stable_between_calls(tmp_path):
    assert load_or_create_key(tmp_path) == load_or_create_key(tmp_path)


def test_fingerprint_is_short_and_stable(tmp_path):
    key = load_or_create_key(tmp_path)
    assert fingerprint(key) == fingerprint(key)
    assert len(fingerprint(key)) == 12


def test_seal_unseal_roundtrip(tmp_path):
    key = load_or_create_key(tmp_path)
    payload = {"identity": "কৌস্তভ", "samples": [{"vector": [0.1] * 128}]}
    envelope = seal(key, payload)
    assert envelope["format"] == "verifyface-template"
    assert unseal(key, envelope) == payload


def test_tampered_payload_is_detected(tmp_path):
    key = load_or_create_key(tmp_path)
    envelope = seal(key, {"a": 1})
    envelope["payload"] = envelope["payload"][:-4] + "AAAA"
    with pytest.raises(TemplateCorruptedError):
        unseal(key, envelope)


def test_wrong_key_is_detected(tmp_path):
    key_a = load_or_create_key(tmp_path)
    envelope = seal(key_a, {"a": 1})
    other = tmp_path / "other"
    with pytest.raises(TemplateCorruptedError):
        unseal(load_or_create_key(other), envelope)


# --------------------------------------------------------------------------- #
# Damage and repair
# --------------------------------------------------------------------------- #
def test_template_file_permissions(fresh_verifier):
    _enroll(fresh_verifier)
    if os.name == "nt":
        pytest.skip("POSIX permissions only")
    path = _template_path(fresh_verifier, "tester")
    assert path.stat().st_mode & 0o777 == 0o600


def test_corrupted_template_is_repaired_from_backup(fresh_verifier):
    v = _enroll(fresh_verifier)
    path = _template_path(v, "tester")

    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"] = envelope["payload"][:-8] + "AAAAAAAA"   # flip bytes
    path.write_text(json.dumps(envelope), encoding="utf-8")

    profile = v.profile("tester")          # auto-repairs
    assert profile.repaired is True
    assert profile.sample_count == 1

    # the live file is healthy again and verification works
    assert v.vault.verify_integrity()[0]["status"] == "ok"
    assert bool(v.verify("tester", fixture_path("person_a_2.jpg"))) is True


def test_unreadable_template_is_reported(fresh_verifier):
    v = _enroll(fresh_verifier)
    path = _template_path(v, "tester")
    path.write_text("{not json", encoding="utf-8")
    report = v.vault.verify_integrity()
    assert report[0]["status"] in {"repaired", "corrupted", "ok"}
    # a backup exists, so reading must still succeed
    assert v.profile("tester").sample_count == 1


def test_total_loss_of_both_files_raises(fresh_verifier):
    v = _enroll(fresh_verifier)
    for path in (v.vault.path / "identities").glob("*.json*"):
        path.write_text("garbage", encoding="utf-8")
    with pytest.raises(TemplateCorruptedError):
        v.profile("tester")


def test_verify_integrity_all_ok(fresh_verifier):
    _enroll(fresh_verifier)
    report = fresh_verifier.vault.verify_integrity()
    assert report and report[0]["status"] == "ok"


# --------------------------------------------------------------------------- #
# Storage safety
# --------------------------------------------------------------------------- #
def test_slugify_blocks_path_traversal():
    for name in ["../evil", "..\\..\\evil", "/etc/passwd", "a/b/c", "....//x"]:
        slug = slugify(name)
        assert "/" not in slug and "\\" not in slug
        assert not slug.startswith(".")
        assert ".." not in slug


def test_slugify_keeps_unicode():
    slug = slugify("কৌস্তভ")
    assert slug.startswith("কৌস্তভ")


def test_slugify_is_collision_free():
    assert slugify("a b") != slugify("a  b")
    assert slugify("name") != slugify("Name")
    assert slugify(" name ") == slugify("name")  # surrounding whitespace is normalised


def test_templates_store_no_photograph(fresh_verifier):
    """The stored record must contain floats — never image bytes."""
    v = _enroll(fresh_verifier)
    path = _template_path(v, "tester")
    raw = path.read_bytes()
    assert b"\xff\xd8\xff" not in raw, "a JPEG header leaked into the template"
    assert b"JFIF" not in raw
    payload = v.profile("tester")
    assert len(payload.centroid) == 128
    assert isinstance(payload.centroid[0], np.floating)


def test_atomic_write_leaves_no_temp_files(fresh_verifier):
    v = _enroll(fresh_verifier)
    leftovers = [p.name for p in (v.vault.path / "identities").iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_delete_removes_everything(fresh_verifier):
    v = _enroll(fresh_verifier)
    assert v.remove("tester") is True
    assert v.remove("tester") is False
    assert list((v.vault.path / "identities").glob("*.json*")) == []
