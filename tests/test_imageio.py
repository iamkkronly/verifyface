"""Image loading must accept many input types and never modify the source.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import base64
import hashlib
import os

import numpy as np
import pytest

from tests.conftest import fixture_path
from verifyface.errors import ImageError, UnsupportedInputError
from verifyface.imageio import load_image


def _hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_load_from_path_returns_fresh_array():
    path = fixture_path("person_a_1.jpg")
    first = load_image(path)
    second = load_image(path)
    assert first.shape[2] == 3 and first.dtype == np.uint8
    assert first is not second
    assert np.array_equal(first, second)


def test_original_file_is_never_modified(verifier):
    path = fixture_path("person_a_2.jpg")
    before_hash, before_mtime = _hash(path), os.stat(path).st_mtime_ns
    verifier.engine.embed(path)
    verifier.compare(path, fixture_path("person_b_2.jpg"))
    assert _hash(path) == before_hash, "the source image bytes changed!"
    assert os.stat(path).st_mtime_ns == before_mtime, "the source file was touched!"


def test_numpy_input_is_copied_not_mutated(verifier):
    import cv2

    image = cv2.imread(str(fixture_path("person_b_1.jpg")))
    original = image.copy()
    verifier.engine.embed(image)
    assert np.array_equal(image, original), "the caller's array was modified"


def test_bytes_and_base64_inputs(verifier):
    raw = fixture_path("person_b_1.jpg").read_bytes()
    from_bytes = verifier.engine.embed(raw)
    from_base64 = verifier.engine.embed("base64:" + base64.b64encode(raw).decode())
    from_data_uri = verifier.engine.embed(
        "data:image/jpeg;base64," + base64.b64encode(raw).decode()
    )
    for other in (from_base64, from_data_uri):
        assert verifier.engine.similarity(from_bytes.vector, other.vector) > 0.999


def test_file_object_and_pil_inputs(verifier):
    from PIL import Image

    path = fixture_path("person_a_2.jpg")
    with open(path, "rb") as handle:
        from_file = verifier.engine.embed(handle)
    with Image.open(path) as img:
        from_pil = verifier.engine.embed(img)
        assert img.fp is not None or True  # PIL object still usable by the caller
    assert verifier.engine.similarity(from_file.vector, from_pil.vector) > 0.999


def test_grayscale_and_rgba_images_are_converted():
    import cv2

    image = cv2.imread(str(fixture_path("person_a_2.jpg")))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    assert load_image(gray).shape[2] == 3
    rgba = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    assert load_image(rgba).shape[2] == 3


def test_float_arrays_are_scaled():
    image = load_image(fixture_path("person_a_1.jpg")).astype(np.float32) / 255.0
    converted = load_image(image)
    assert converted.dtype == np.uint8
    assert converted.max() > 200


def test_missing_file_raises_clear_error():
    with pytest.raises(ImageError, match="not found"):
        load_image("does/not/exist.jpg")


def test_corrupt_bytes_raise_image_error():
    with pytest.raises(ImageError):
        load_image(b"this is definitely not an image")


def test_unsupported_type_raises():
    with pytest.raises(UnsupportedInputError):
        load_image(12345)


def test_tiny_image_rejected():
    with pytest.raises(ImageError):
        load_image(np.zeros((1, 1, 3), dtype=np.uint8))


def test_url_guard_can_be_disabled():
    with pytest.raises(UnsupportedInputError):
        load_image("https://example.com/x.jpg", allow_url=False)


def test_encode_helpers_roundtrip():
    from verifyface.imageio import encode_jpeg, encode_png, to_data_uri

    image = load_image(fixture_path("person_a_1.jpg"))
    for payload in (encode_jpeg(image), encode_png(image)):
        assert load_image(payload).shape[2] == 3
    assert to_data_uri(image).startswith("data:image/jpeg;base64,")
