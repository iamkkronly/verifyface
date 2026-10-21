"""Smoke tests: the package imports, models are intact, credit is present.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import hashlib

import pytest


def test_metadata_and_credit():
    import re

    import verifyface as vf

    assert re.fullmatch(r"\d+\.\d+\.\d+", vf.__version__)
    assert vf.__author__ == "Kaustav Kanti Ray"
    assert vf.__developer__ == "Kaustav Kanti Ray"
    assert "Kaustav Kanti Ray" in vf.BANNER
    assert "Kaustav Kanti Ray" in vf.COPYRIGHT
    assert vf.__license__ == "MIT"
    assert "Kaustav Kanti Ray" in vf.credits()


def test_public_api_surface():
    import verifyface as vf

    for name in ("enroll", "verify", "identify", "compare", "same_person", "Verifier"):
        assert callable(getattr(vf, name))
    assert vf.LiveSession is not None
    assert callable(vf.scan_live)
    assert vf.liveness.ACTIONS


def test_bundled_models_are_valid(verifier):
    info = verifier.engine.info()
    assert info["developer"] == "Kaustav Kanti Ray"
    assert info["embedding_size"] == 128
    for kind, model in info["models"].items():
        assert model["valid"] is True, f"{kind} failed its checksum"
        assert model["size_mb"] > 0.05


def test_model_checksums_match_constants():
    from verifyface.engine import MODEL_FILES, MODEL_SHA256, bundled_model_dir

    assert set(MODEL_FILES) == {"detector", "recognizer"}
    for kind, filename in MODEL_FILES.items():
        path = bundled_model_dir() / filename
        assert path.is_file(), f"{filename} is missing from the wheel"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == MODEL_SHA256[kind]


def test_engine_embedding_is_normalised(verifier):
    import numpy as np

    from tests.conftest import fixture_path

    embedding = verifier.engine.embed(fixture_path("person_a_1.jpg"))
    assert embedding.vector.shape == (128,)
    assert embedding.vector.dtype == np.float32
    assert abs(float(np.linalg.norm(embedding.vector)) - 1.0) < 1e-5


def test_default_vault_is_user_scoped():
    import verifyface as vf

    path = vf.default_vault_path()
    assert path.name == "vault"
    assert "verifyface" in str(path).lower()


def test_threshold_presets_are_ordered():
    import verifyface as vf

    presets = vf.THRESHOLD_PRESETS
    assert presets["lenient"] < presets["balanced"] < presets["strict"]


@pytest.mark.parametrize("value,expected", [("strict", 0.48), ("balanced", 0.40), ("lenient", 0.33)])
def test_resolve_threshold(value, expected):
    from verifyface.config import resolve_threshold

    assert resolve_threshold(value) == pytest.approx(expected)


def test_invalid_threshold_rejected():
    from verifyface.config import resolve_threshold
    from verifyface.errors import ConfigError

    with pytest.raises(ConfigError):
        resolve_threshold("impossible")
    with pytest.raises(ConfigError):
        resolve_threshold(1.5)
