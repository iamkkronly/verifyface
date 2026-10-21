"""Read-only image loading.

The single most important rule in this module: **an input image is never
modified.**  Files are opened read-only, bytes are decoded into a fresh array,
and arrays handed to us by the caller are copied before any processing happens.
That is what makes it impossible for verifyface to "corrupt" a person's face
photo while it is being scanned.

Supported inputs
    * file paths (``str`` / :class:`os.PathLike`) — unicode paths work on Windows
    * ``bytes`` / ``bytearray`` / ``memoryview`` (uploaded file content)
    * ``numpy`` arrays (BGR, as OpenCV uses; RGB is detected heuristically)
    * :class:`PIL.Image.Image`
    * open file objects
    * ``http(s)://`` URLs and ``data:image/...;base64,`` URIs
    * base64 strings

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import base64
import binascii
import io
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np

from .errors import ImageError, UnsupportedInputError

try:  # Pillow is a hard dependency, but never make imports fatal.
    from PIL import Image, ImageOps

    _HAS_PIL = True
except Exception:  # pragma: no cover
    _HAS_PIL = False

MAX_URL_BYTES = 25 * 1024 * 1024  # 25 MB safety cap for remote images

ImageSource = Union[str, bytes, bytearray, memoryview, np.ndarray, "os.PathLike[str]", Any]


def _decode_bytes(data: bytes, *, origin: str = "") -> np.ndarray:
    """Decode raw image bytes into a BGR uint8 array, honouring EXIF rotation."""
    if not data:
        raise ImageError(f"The image is empty{origin and ' (' + origin + ')'}.")

    if _HAS_PIL:
        try:
            with Image.open(io.BytesIO(data)) as img:
                img = ImageOps.exif_transpose(img)  # phone selfies are often rotated
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                array = np.asarray(img)
                if array.ndim == 2:
                    bgr = np.stack([array] * 3, axis=-1)
                else:
                    bgr = array[:, :, ::-1]
                return np.ascontiguousarray(bgr, dtype=np.uint8)
        except ImageError:
            raise
        except Exception:
            pass  # fall through to OpenCV, which reads a few odd formats better

    import cv2

    array = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if array is None:
        raise ImageError(
            f"Could not decode the image{origin and ' (' + origin + ')'}. "
            "It may be corrupt or in an unsupported format."
        )
    return array


def _from_url(url: str, *, timeout: float = 15.0) -> np.ndarray:
    if url.startswith("data:"):
        header, _, payload = url.partition(",")
        if ";base64" not in header:
            raise ImageError("Only base64 data URIs are supported.")
        try:
            return _decode_bytes(base64.b64decode(payload, validate=False), origin="data URI")
        except (binascii.Error, ValueError) as exc:
            raise ImageError(f"Invalid base64 data URI: {exc}") from None

    request = urllib.request.Request(url, headers={"User-Agent": "verifyface/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            data = response.read(MAX_URL_BYTES + 1)
    except Exception as exc:
        raise ImageError(f"Could not download the image from {url}: {exc}") from None
    if len(data) > MAX_URL_BYTES:
        raise ImageError(f"Remote image is larger than {MAX_URL_BYTES // (1024 * 1024)} MB.")
    return _decode_bytes(data, origin=url)


def _from_array(array: np.ndarray, *, assume_bgr: bool = True) -> np.ndarray:
    """Normalise a numpy image *without touching the caller's array*."""
    if not isinstance(array, np.ndarray):
        raise UnsupportedInputError(f"Expected a numpy array, got {type(array).__name__}.")

    # Always copy: downstream code may write into the buffer.
    work = np.array(array, copy=True, subok=False)

    if work.ndim == 2:
        work = np.stack([work] * 3, axis=-1)
    elif work.ndim == 3 and work.shape[2] == 4:
        work = work[:, :, :3]
    elif work.ndim == 3 and work.shape[2] == 1:
        work = np.repeat(work, 3, axis=2)
    elif work.ndim != 3 or work.shape[2] != 3:
        raise ImageError(
            f"Unsupported array shape {work.shape}. Expected (H, W), (H, W, 3) or (H, W, 4)."
        )

    if work.dtype != np.uint8:
        if np.issubdtype(work.dtype, np.floating):
            max_value = float(np.nanmax(work)) if work.size else 0.0
            scale = 255.0 if max_value <= 1.0 else 1.0
            work = np.clip(work * scale, 0, 255).astype(np.uint8)
        else:
            work = np.clip(work, 0, 255).astype(np.uint8)

    if not assume_bgr and work.shape[2] == 3:
        work = work[:, :, ::-1]

    if work.shape[0] < 2 or work.shape[1] < 2:
        raise ImageError(f"Image is too small: {work.shape[1]}x{work.shape[0]} pixels.")

    return np.ascontiguousarray(work)


def load_image(source: ImageSource, *, allow_url: bool = True) -> np.ndarray:
    """Load ``source`` and return a **new** BGR ``uint8`` numpy array.

    The returned array is always safe to modify; the original file, bytes,
    PIL image or numpy array is left exactly as it was.
    """
    # -- numpy arrays ---------------------------------------------------- #
    if isinstance(source, np.ndarray):
        return _from_array(source)

    # -- bytes-like ------------------------------------------------------ #
    if isinstance(source, (bytes, bytearray, memoryview)):
        return _decode_bytes(bytes(source), origin="bytes")

    # -- PIL image ------------------------------------------------------- #
    if _HAS_PIL and isinstance(source, Image.Image):
        img = source.copy()  # never mutate the caller's image object
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        return _from_array(np.asarray(img), assume_bgr=False)

    # -- file-like objects ----------------------------------------------- #
    if hasattr(source, "read") and not isinstance(source, (str, bytes, Path)):
        data = source.read()
        if isinstance(data, str):
            raise UnsupportedInputError("The file object returned text, not bytes.")
        return _decode_bytes(bytes(data), origin=getattr(source, "name", "") or "file object")

    # -- strings: URL, data URI, base64, or path -------------------------- #
    if isinstance(source, str):
        text = source.strip()
        lowered = text.lower()
        if lowered.startswith(("http://", "https://", "data:")):
            if not allow_url:
                raise UnsupportedInputError("URL inputs are disabled (allow_url=False).")
            return _from_url(text)
        if text.startswith("base64:"):
            try:
                return _decode_bytes(base64.b64decode(text[7:]), origin="base64")
            except (binascii.Error, ValueError) as exc:
                raise ImageError(f"Invalid base64 image: {exc}") from None
        return load_image(Path(text), allow_url=allow_url)

    # -- paths ------------------------------------------------------------ #
    if isinstance(source, os.PathLike):
        path = Path(source).expanduser()
        if not path.exists():
            raise ImageError(f"Image not found: {path}")
        if path.is_dir():
            raise ImageError(f"Expected an image file but got a directory: {path}")
        try:
            data = path.read_bytes()  # read-only; the file is never opened for writing
        except OSError as exc:
            raise ImageError(f"Could not read {path}: {exc}") from None
        return _decode_bytes(data, origin=str(path))

    raise UnsupportedInputError(
        f"Cannot read an image from {type(source).__name__}. "
        "Pass a path, URL, bytes, PIL image, file object or numpy array."
    )


def encode_jpeg(array: np.ndarray, quality: int = 90) -> bytes:
    """Encode a BGR array as JPEG bytes (used by the camera / web helpers)."""
    import cv2

    ok, buffer = cv2.imencode(".jpg", array, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise ImageError("Could not encode the frame as JPEG.")
    return buffer.tobytes()


def encode_png(array: np.ndarray) -> bytes:
    """Encode a BGR array as PNG bytes."""
    import cv2

    ok, buffer = cv2.imencode(".png", array)
    if not ok:
        raise ImageError("Could not encode the frame as PNG.")
    return buffer.tobytes()


def to_data_uri(array: np.ndarray, *, fmt: str = "jpeg", quality: int = 88) -> str:
    """Return a ``data:image/...;base64,`` URI, handy for web previews."""
    payload = encode_jpeg(array, quality) if fmt == "jpeg" else encode_png(array)
    mime = "image/jpeg" if fmt == "jpeg" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


def is_url(value: object) -> bool:
    """True when ``value`` looks like a URL or a data URI."""
    return isinstance(value, str) and value.strip().lower().startswith(
        ("http://", "https://", "data:")
    )


def quote_path(path: Path) -> str:
    """Quote a path for safe display in logs/messages."""
    return urllib.parse.quote(str(path))


__all__ = ["load_image", "encode_jpeg", "encode_png", "to_data_uri", "is_url", "quote_path"]
