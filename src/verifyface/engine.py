"""The face engine: detect → align → embed → compare.

Two small neural networks do all the work, both run by OpenCV itself (no
PyTorch, no TensorFlow, no onnxruntime):

``face_detection_yunet``
    YuNet finds up to 5000 faces per frame and returns five landmarks.
``face_recognition_sface``
    SFace turns an aligned 112x112 face into a 128-number identity vector.

Both models are bundled inside the wheel, so ``pip install verifyface`` works
offline, on Windows, macOS, Linux and Raspberry Pi alike.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import hashlib
import os
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import _meta
from .config import Settings, default_home, user_cache_dir
from .errors import ModelNotFoundError, NoFaceFoundError
from .imageio import load_image
from .preprocess import (
    DetectedFace,
    FaceDetector,
    QualityReport,
    align_face,
    assess_quality,
    select_face,
)

MODEL_FILES = {
    "detector": "face_detection_yunet_2023mar_int8bq.onnx",
    "recognizer": "face_recognition_sface_2021dec_int8bq.onnx",
}

MODEL_URLS = {
    "detector": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
        "face_detection_yunet_2023mar_int8bq.onnx"
    ),
    "recognizer": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/"
        "face_recognition_sface_2021dec_int8bq.onnx"
    ),
}

MODEL_SHA256 = {
    "detector": "49f000ec501fef24739071fc7e68267d32209045b6822c0c72dce1da25726f10",
    "recognizer": "fb143eea07838aa532d1c95df5f69899974ea0140e1fba05e94204be13ed74ee",
}

EMBEDDING_SIZE = 128

#: Name of the single input tensor of both ONNX models (OpenCV 5 needs it).
_INPUT_LAYER_NAME = "data"


def opencv_major_version() -> int:
    """Major version of the installed OpenCV (4 or 5 …), 4 when unknown."""
    try:
        import cv2

        return int(str(cv2.__version__).split(".")[0])
    except Exception:  # pragma: no cover
        return 4


# --------------------------------------------------------------------------- #
# Model location
# --------------------------------------------------------------------------- #
def bundled_model_dir() -> Path:
    """Folder with the models that ship inside the installed wheel."""
    return Path(__file__).resolve().parent / "models"


def _valid(path: Path, kind: str, *, verify_hash: bool = True) -> bool:
    if not path.is_file() or path.stat().st_size < 50_000:
        return False
    if not verify_hash:
        return True
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest == MODEL_SHA256[kind]


def download_models(target: Optional[Path] = None, *, force: bool = False) -> Path:
    """Download the two ONNX models into ``target`` (defaults to the cache).

    Returns the folder that now contains them.  Used automatically the first
    time a *source checkout* runs without bundled weights.
    """
    folder = Path(target).expanduser() if target else user_cache_dir()
    folder.mkdir(parents=True, exist_ok=True)
    for kind, filename in MODEL_FILES.items():
        destination = folder / filename
        if not force and _valid(destination, kind):
            continue
        temporary = destination.with_suffix(".part")
        try:
            request = urllib.request.Request(
                MODEL_URLS[kind], headers={"User-Agent": f"verifyface/{_meta.__version__}"}
            )
            with urllib.request.urlopen(request, timeout=120) as response, open(
                temporary, "wb"
            ) as handle:
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    handle.write(chunk)
            os.replace(temporary, destination)
        except Exception as exc:  # pragma: no cover - network dependent
            temporary.unlink(missing_ok=True)
            raise ModelNotFoundError(
                f"Could not download {filename}: {exc}"
            ) from None
        if not _valid(destination, kind):
            destination.unlink(missing_ok=True)
            raise ModelNotFoundError(
                f"Downloaded {filename} failed its checksum check; refusing to use it."
            )
    return folder


def resolve_model_dir(
    explicit: Optional[Path] = None,
    *,
    allow_download: bool = True,
    create: bool = True,
) -> Path:
    """Find a folder containing both models, in a predictable order."""
    candidates: List[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit).expanduser())
    env_dir = os.environ.get("VERIFYFACE_MODEL_DIR")
    if env_dir:
        candidates.append(Path(env_dir).expanduser())
    candidates.append(bundled_model_dir())
    candidates.append(user_cache_dir())
    candidates.append(default_home() / "models")

    for folder in candidates:
        if all((folder / name).is_file() for name in MODEL_FILES.values()):
            return folder

    if allow_download:
        target = user_cache_dir()
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return download_models(target)
    raise ModelNotFoundError(
        "The face models were not found in: " + ", ".join(str(c) for c in candidates)
    )


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
@dataclass
class Embedding:
    """A 128-dimensional, unit-length identity vector plus its provenance."""

    vector: np.ndarray
    quality: QualityReport
    face: Optional[DetectedFace] = None
    source: str = ""

    def __post_init__(self) -> None:
        vector = np.asarray(self.vector, dtype=np.float32).reshape(-1)
        if vector.size != EMBEDDING_SIZE:
            raise ValueError(f"Expected a {EMBEDDING_SIZE}-d vector, got {vector.size}.")
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector = vector / norm
        self.vector = np.ascontiguousarray(vector, dtype=np.float32)

    # -- serialisation -------------------------------------------------- #
    def tolist(self) -> List[float]:
        return [round(float(v), 6) for v in self.vector]

    def __array__(self, dtype=None):  # pragma: no cover - convenience
        return self.vector if dtype is None else self.vector.astype(dtype)

    def __len__(self) -> int:
        return int(self.vector.size)


@dataclass
class CompareResult:
    """Outcome of comparing two images (or two embeddings)."""

    matched: bool
    score: float
    threshold: float
    confidence: float
    quality_a: Optional[QualityReport] = None
    quality_b: Optional[QualityReport] = None
    threshold_name: str = "balanced"

    def __bool__(self) -> bool:
        return self.matched

    def as_dict(self) -> dict:
        return {
            "matched": self.matched,
            "score": round(self.score, 4),
            "threshold": self.threshold,
            "confidence": round(self.confidence, 4),
            "threshold_name": self.threshold_name,
            "quality": {
                "a": self.quality_a.as_dict() if self.quality_a else None,
                "b": self.quality_b.as_dict() if self.quality_b else None,
            },
        }

    def explain(self) -> str:
        verdict = "SAME person" if self.matched else "NOT the same person"
        return (
            f"{verdict} — similarity {self.score:.3f} vs threshold {self.threshold:.3f} "
            f"({self.confidence * 100:.1f}% confidence, {self.threshold_name} profile)"
        )


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
class FaceEngine:
    """Stateless, thread-safe face engine.

    Example
    -------
    >>> import verifyface as vf
    >>> engine = vf.FaceEngine()
    >>> result = engine.compare("a.jpg", "b.jpg")
    >>> result.matched
    True
    """

    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        model_dir: Optional[Path] = None,
        detection_confidence: float = 0.6,
    ) -> None:
        self.settings = settings or Settings()
        self._model_dir = model_dir
        self._detection_confidence = detection_confidence
        self._lock = threading.Lock()
        self._local = threading.local()
        self._detector: Optional[FaceDetector] = None
        self._resolved_dir: Optional[Path] = None

    # -- lazy resources -------------------------------------------------- #
    @property
    def model_dir(self) -> Path:
        if self._resolved_dir is None:
            self._resolved_dir = resolve_model_dir(
                self._model_dir if self._model_dir else self.settings.model_dir,
                allow_download=self.settings.allow_download,
            )
        return self._resolved_dir

    @property
    def detector(self) -> FaceDetector:
        if self._detector is None:
            with self._lock:
                if self._detector is None:
                    self._detector = FaceDetector(
                        self.model_dir / MODEL_FILES["detector"],
                        confidence=self._detection_confidence,
                    )
        return self._detector

    def _recognizer(self):
        import cv2

        net = getattr(self._local, "net", None)
        if net is None:
            net = cv2.dnn.readNetFromONNX(str(self.model_dir / MODEL_FILES["recognizer"]))
            if opencv_major_version() < 5:
                # OpenCV 5's graph engine handles placement itself and warns on targets
                try:
                    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                except Exception:  # pragma: no cover - exotic builds
                    pass
            self._local.net = net
            self._local.input_style = None
        return net

    def _feed(self, net, blob) -> None:
        """Feed a blob, adapting to the OpenCV 4.x vs 5.x DNN APIs."""
        style = getattr(self._local, "input_style", None)
        import cv2

        if style is None:
            attempts = ("named", "plain") if opencv_major_version() >= 5 else ("plain", "named")
        else:
            attempts = (style,)

        last_error: Optional[Exception] = None
        for attempt in attempts:
            try:
                if attempt == "named":
                    net.setInput(blob, _INPUT_LAYER_NAME)
                else:
                    net.setInput(blob)
                self._local.input_style = attempt
                return
            except cv2.error as exc:  # pragma: no cover - version dependent
                last_error = exc
        if last_error is not None:
            raise last_error

    def warmup(self) -> "FaceEngine":
        """Load models and run one dummy pass (useful before timing)."""
        dummy = np.full((240, 320, 3), 127, dtype=np.uint8)
        self.detector.detect(dummy)
        self._recognizer()
        return self

    # -- single image ---------------------------------------------------- #
    def detect_faces(self, image) -> List[DetectedFace]:
        """Return all faces found in an image source."""
        return self.detector.detect(load_image(image))

    def embed(
        self,
        image,
        *,
        mode: str = "largest",
        check_quality: bool = True,
        strict_quality: bool = False,
    ) -> Embedding:
        """Turn one photo into an identity :class:`Embedding`.

        Parameters
        ----------
        image
            Any source accepted by :func:`verifyface.load_image`.
        mode
            ``largest`` (default), ``strict`` or ``center`` — which face to use.
        check_quality
            Measure blur/exposure/pose (always recommended).
        strict_quality
            Raise :class:`LowQualityError` instead of returning a weak embedding.
        """
        from .errors import LowQualityError

        pixels = load_image(image)  # a private copy: the input is never touched
        faces = self.detector.detect(pixels)
        face = select_face(faces, mode=mode, min_size=self.settings.min_face_size)
        aligned = align_face(pixels, face, size=112)

        quality = assess_quality(
            pixels,
            face,
            aligned,
            min_sharpness=self.settings.min_sharpness,
            min_brightness=self.settings.min_brightness,
            max_brightness=self.settings.max_brightness,
            max_yaw=self.settings.max_yaw_degrees,
            max_roll=self.settings.max_roll_degrees,
        )
        if not quality.passed:
            if strict_quality:
                raise LowQualityError(
                    f"Face quality is too low to verify safely: {', '.join(quality.issues)}.",
                    hint="Hold still, face the camera, and make sure the face is well lit.",
                )
            # Slightly unfavourable conditions are tolerated, see the docs.
            if "too small" in " ".join(quality.issues):
                raise LowQualityError(
                    "The face is too small in the frame.", hint="Move closer to the camera."
                )

        vector = self._forward(aligned)
        return Embedding(
            vector=vector,
            quality=quality,
            face=face,
            source=str(image) if isinstance(image, (str, os.PathLike)) else "",
        )

    def embed_many(self, images: Sequence, **kwargs) -> List[Embedding]:
        """Embed several photos, skipping (and reporting) the unusable ones."""
        results: List[Embedding] = []
        for item in images:
            try:
                results.append(self.embed(item, **kwargs))
            except NoFaceFoundError:
                continue
        if not results:
            raise NoFaceFoundError("None of the supplied images contained a usable face.")
        return results

    def _forward(self, aligned_bgr: np.ndarray) -> np.ndarray:
        import cv2

        # IMPORTANT: SFace expects raw BGR values in 0..255 (scale = 1.0).
        blob = cv2.dnn.blobFromImage(
            aligned_bgr, 1.0, (112, 112), (0.0, 0.0, 0.0), swapRB=False, crop=False
        )
        net = self._recognizer()
        self._feed(net, blob)
        output = net.forward().reshape(-1).astype(np.float32)
        norm = float(np.linalg.norm(output))
        if norm < 1e-12:
            raise NoFaceFoundError("The recognizer produced an empty embedding.")
        return output / norm

    # -- comparison ------------------------------------------------------ #
    @staticmethod
    def similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity of two embeddings, in ``[-1, 1]``."""
        va = np.asarray(a, dtype=np.float32).reshape(-1)
        vb = np.asarray(b, dtype=np.float32).reshape(-1)
        na, nb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
        if na < 1e-12 or nb < 1e-12:
            return 0.0
        return float(np.clip(np.dot(va, vb) / (na * nb), -1.0, 1.0))

    def compare(self, image_a, image_b, *, threshold: Optional[float] = None) -> CompareResult:
        """Compare two photos and decide whether they show the same person."""
        from .similarity import confidence_from_score, resolve_profile

        emb_a = self.embed(image_a)
        emb_b = self.embed(image_b)
        score = self.similarity(emb_a.vector, emb_b.vector)
        cutoff, name = resolve_profile(threshold, self.settings.threshold)
        return CompareResult(
            matched=bool(score >= cutoff),
            score=score,
            threshold=cutoff,
            confidence=confidence_from_score(score, cutoff),
            quality_a=emb_a.quality,
            quality_b=emb_b.quality,
            threshold_name=name,
        )

    # -- gallery helpers -------------------------------------------------- #
    @staticmethod
    def centroid(embeddings: Sequence[Embedding]) -> np.ndarray:
        """Unit-length mean of several embeddings (multi-photo enrollment)."""
        if not embeddings:
            raise ValueError("centroid() needs at least one embedding")
        matrix = np.stack([e.vector for e in embeddings]).astype(np.float32)
        mean = matrix.mean(axis=0)
        norm = float(np.linalg.norm(mean))
        return mean / norm if norm > 1e-12 else mean

    def best_match(
        self,
        probe: Embedding,
        gallery: Dict[str, np.ndarray],
        *,
        threshold: Optional[float] = None,
    ) -> Tuple[Optional[str], float]:
        """Return the closest enrolled identity and its score."""
        from .similarity import resolve_profile

        cutoff, _ = resolve_profile(threshold, self.settings.threshold)
        best_name: Optional[str] = None
        best_score = -1.0
        for name, vector in gallery.items():
            score = self.similarity(probe.vector, vector)
            if score > best_score:
                best_name, best_score = name, score
        if best_name is None or best_score < cutoff:
            return None, max(best_score, 0.0)
        return best_name, best_score

    # -- introspection ---------------------------------------------------- #
    def info(self) -> dict:
        info = {
            "developer": _meta.__author__,
            "version": _meta.__version__,
            "embedding_size": EMBEDDING_SIZE,
            "model_dir": str(self.model_dir),
            "models": {},
        }
        for kind, filename in MODEL_FILES.items():
            path = self.model_dir / filename
            info["models"][kind] = {
                "file": filename,
                "size_mb": round(path.stat().st_size / (1024 * 1024), 2) if path.exists() else None,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
                "valid": _valid(path, kind) if path.exists() else False,
            }
        return info


__all__ = [
    "FaceEngine",
    "Embedding",
    "CompareResult",
    "MODEL_FILES",
    "MODEL_SHA256",
    "download_models",
    "resolve_model_dir",
    "bundled_model_dir",
    "EMBEDDING_SIZE",
]
