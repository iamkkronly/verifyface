"""Face detection, alignment and quality control.

The alignment step is what makes verification survive real life: the same
person photographed years apart, in different clothes, in different places, at
different angles, is geometrically normalised onto the same 112x112 canvas
before a single feature is computed.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .errors import LowQualityError, MultipleFacesError, NoFaceFoundError

# Canonical ArcFace 5-point template for a 112x112 crop.
ARCFACE_TEMPLATE = np.array(
    [
        [38.2946, 51.6963],   # right eye (subject's right → image left)
        [73.5318, 51.5014],   # left eye
        [56.0252, 71.7366],   # nose tip
        [41.5493, 92.3655],   # right mouth corner
        [70.7299, 92.2041],   # left mouth corner
    ],
    dtype=np.float32,
)

DETECT_MAX_SIDE = 1200  # downscale very large photos before detection (speed)


@dataclass(frozen=True)
class DetectedFace:
    """One detected face and its five landmarks."""

    box: Tuple[float, float, float, float]  # x, y, w, h
    landmarks: np.ndarray                   # shape (5, 2)
    score: float

    @property
    def width(self) -> float:
        return self.box[2]

    @property
    def height(self) -> float:
        return self.box[3]

    @property
    def area(self) -> float:
        return self.box[2] * self.box[3]

    @property
    def center(self) -> Tuple[float, float]:
        return (self.box[0] + self.box[2] / 2.0, self.box[1] + self.box[3] / 2.0)


@dataclass(frozen=True)
class QualityReport:
    """Objective, explainable measurements about a face crop."""

    passed: bool
    score: float                       # 0..1 overall quality
    sharpness: float
    brightness: float
    face_ratio: float                  # face width / image width
    yaw: float                         # degrees, 0 = straight ahead
    roll: float                        # degrees
    issues: Tuple[str, ...] = field(default_factory=tuple)

    def describe(self) -> str:
        if self.passed:
            return f"good quality (score {self.score:.2f})"
        return "quality problems: " + ", ".join(self.issues)

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": round(self.score, 4),
            "sharpness": round(self.sharpness, 2),
            "brightness": round(self.brightness, 2),
            "face_ratio": round(self.face_ratio, 4),
            "yaw": round(self.yaw, 2),
            "roll": round(self.roll, 2),
            "issues": list(self.issues),
        }


class FaceDetector:
    """Thin, thread-safe wrapper around OpenCV's YuNet detector.

    Each thread gets its own detector instance because OpenCV DNN objects are
    not thread safe.  This keeps the library safe inside web servers.
    """

    def __init__(self, model_path: Path, *, confidence: float = 0.6) -> None:
        self.model_path = Path(model_path)
        self.confidence = float(confidence)
        self._local = threading.local()

    # ------------------------------------------------------------------ #
    def _instance(self):
        import cv2

        detector = getattr(self._local, "detector", None)
        if detector is None:
            detector = cv2.FaceDetectorYN.create(
                str(self.model_path),
                "",
                (320, 320),
                self.confidence,
                0.3,      # NMS threshold
                5000,     # top-k
            )
            self._local.detector = detector
        return detector

    # ------------------------------------------------------------------ #
    def detect(self, image: np.ndarray) -> List[DetectedFace]:
        """Return every face found in ``image`` (BGR), in a private copy."""
        import cv2

        if image is None or image.size == 0:
            return []

        height, width = image.shape[:2]
        scale = 1.0
        longest = max(height, width)
        work = image
        if longest > DETECT_MAX_SIDE:
            scale = DETECT_MAX_SIDE / float(longest)
            work = cv2.resize(
                image,
                (max(1, int(width * scale)), max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )

        detector = self._instance()
        detector.setInputSize((work.shape[1], work.shape[0]))
        try:
            _, raw = detector.detect(work)
        except cv2.error:  # pragma: no cover - unusual builds
            return []
        if raw is None or len(raw) == 0:
            return []

        faces: List[DetectedFace] = []
        for row in np.asarray(raw, dtype=np.float32):
            x, y, w, h = row[:4]
            landmarks = row[4:14].reshape(5, 2).astype(np.float32)
            if scale != 1.0:
                x, y, w, h = x / scale, y / scale, w / scale, h / scale
                landmarks = landmarks / scale
            if w <= 1 or h <= 1:
                continue
            faces.append(
                DetectedFace(
                    box=(float(x), float(y), float(w), float(h)),
                    landmarks=landmarks,
                    score=float(row[14]) if len(row) > 14 else 1.0,
                )
            )
        faces.sort(key=lambda f: f.area, reverse=True)
        return faces


def select_face(
    faces: Sequence[DetectedFace],
    *,
    mode: str = "largest",
    min_size: int = 0,
) -> DetectedFace:
    """Pick one face according to ``mode``.

    ``largest`` (default) — the biggest face, the usual selfie case.
    ``strict``            — refuse when there is more than one person.
    ``center``            — the face closest to the centre of the frame.
    """
    if not faces:
        raise NoFaceFoundError("No face was detected in the image.")

    candidates = [f for f in faces if min(f.width, f.height) >= min_size] if min_size else list(faces)
    if not candidates:
        smallest = min(min(f.width, f.height) for f in faces)
        raise LowQualityError(
            f"The face is too small ({smallest:.0f} px). Move closer or use a higher "
            f"resolution photo (at least {min_size} px)."
        )

    if mode == "strict":
        if len(candidates) > 1:
            raise MultipleFacesError(
                f"Found {len(candidates)} faces. Use mode='largest' or a close-up photo."
            )
        return candidates[0]

    if mode == "center":
        def distance(face: DetectedFace) -> float:
            return face.center[0] ** 2 + face.center[1] ** 2

        # centre distances are relative to the frame centre once normalised
        return min(candidates, key=distance)

    if mode != "largest":
        raise ValueError(f"Unknown mode {mode!r}. Use 'largest', 'strict' or 'center'.")

    return max(candidates, key=lambda f: f.area)


# --------------------------------------------------------------------------- #
# Alignment
# --------------------------------------------------------------------------- #
def _umeyama(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Least-squares similarity transform (scale + rotation + translation).

    Used as a dependency-free fallback when OpenCV's estimator refuses to
    converge; guarantees we always produce *some* sane alignment.
    """
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_demean = src - src_mean
    dst_demean = dst - dst_mean

    covariance = dst_demean.T @ src_demean / src.shape[0]
    u, s, vt = np.linalg.svd(covariance)
    rank = np.linalg.matrix_rank(covariance)
    d = np.ones(3)
    if rank == 2 and np.linalg.det(u) * np.linalg.det(vt) < 0:
        d[2] = -1
    rotation = u @ np.diag(d) @ vt

    var_src = src_demean.var(axis=0).sum()
    scale = 1.0 if var_src <= 1e-12 else (s @ d) / var_src
    translation = dst_mean - scale * (rotation @ src_mean)

    matrix = np.eye(3, dtype=np.float64)
    matrix[:2, :2] = scale * rotation
    matrix[:2, 2] = translation
    return matrix[:2].astype(np.float32)


def estimate_alignment(landmarks: np.ndarray, size: int = 112) -> np.ndarray:
    """Return the 2x3 affine matrix that maps ``landmarks`` onto the template."""
    import cv2

    src = np.asarray(landmarks, dtype=np.float32).reshape(5, 2)
    dst = ARCFACE_TEMPLATE * (size / 112.0)

    matrix = None
    try:
        matrix, _ = cv2.estimateAffinePartial2D(
            src, dst, method=cv2.LMEDS, maxIters=2000, confidence=0.995, refineIters=10
        )
    except cv2.error:  # pragma: no cover
        matrix = None
    if matrix is None or not np.all(np.isfinite(matrix)):
        matrix = _umeyama(src, dst)
    return np.asarray(matrix, dtype=np.float32)


def align_face(image: np.ndarray, face: DetectedFace, size: int = 112) -> np.ndarray:
    """Warp ``image`` so the detected face matches the canonical template.

    The source array is never modified; a new square crop is returned.
    """
    import cv2

    matrix = estimate_alignment(face.landmarks, size)
    aligned = cv2.warpAffine(
        image,
        matrix,
        (size, size),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return aligned


# --------------------------------------------------------------------------- #
# Quality
# --------------------------------------------------------------------------- #
def _estimate_pose(landmarks: np.ndarray) -> Tuple[float, float]:
    """Rough yaw / roll (degrees) from the five landmarks."""
    right_eye, left_eye, nose, right_mouth, left_mouth = np.asarray(landmarks, dtype=np.float64)

    eye_dx = left_eye[0] - right_eye[0]
    eye_dy = left_eye[1] - right_eye[1]
    roll = float(np.degrees(np.arctan2(eye_dy, eye_dx if eye_dx else 1e-6)))

    eye_mid = (right_eye + left_eye) / 2.0
    mouth_mid = (right_mouth + left_mouth) / 2.0
    eye_span = max(abs(left_eye[0] - right_eye[0]), 1e-6)
    # 0.0 = nose over the right eye, 0.5 = centred (straight ahead), 1.0 = left eye
    ratio = (nose[0] - right_eye[0]) / eye_span
    yaw = float(np.clip((ratio - 0.5) * 160.0, -90.0, 90.0))

    # a strong pitch (looking down/up) also collapses the eye-to-mouth distance
    face_height = max(abs(mouth_mid[1] - eye_mid[1]), 1e-6)
    pitch_ratio = (nose[1] - eye_mid[1]) / face_height
    if pitch_ratio < 0.28 or pitch_ratio > 0.72:
        yaw = max(yaw, 45.0) if yaw >= 0 else min(yaw, -45.0)

    return yaw, roll


def assess_quality(
    image: np.ndarray,
    face: DetectedFace,
    aligned: Optional[np.ndarray] = None,
    *,
    min_sharpness: float = 12.0,
    min_brightness: float = 35.0,
    max_brightness: float = 235.0,
    max_yaw: float = 38.0,
    max_roll: float = 30.0,
) -> QualityReport:
    """Measure blur, exposure, face size and pose; never raises."""
    import cv2

    if aligned is None:
        aligned = align_face(image, face, 112)

    gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY) if aligned.ndim == 3 else aligned
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    image_width = max(float(image.shape[1]), 1.0)
    face_ratio = float(face.width / image_width)
    yaw, roll = _estimate_pose(face.landmarks)

    issues: List[str] = []
    if sharpness < min_sharpness:
        issues.append("blurry")
    if brightness < min_brightness:
        issues.append("too dark")
    if brightness > max_brightness:
        issues.append("over-exposed")
    if abs(yaw) > max_yaw:
        issues.append("head turned too far")
    if abs(roll) > max_roll:
        issues.append("head tilted")
    if face_ratio < 0.05:
        issues.append("face too small in frame")

    score = 1.0
    score -= min(1.0, max(0.0, (min_sharpness - sharpness) / max(min_sharpness, 1e-6))) * 0.45
    if brightness < min_brightness or brightness > max_brightness:
        score -= 0.35
    score -= min(1.0, abs(yaw) / 90.0) * 0.25
    score -= min(1.0, abs(roll) / 90.0) * 0.15
    score = float(np.clip(score, 0.0, 1.0))

    return QualityReport(
        passed=not issues,
        score=score,
        sharpness=sharpness,
        brightness=brightness,
        face_ratio=face_ratio,
        yaw=yaw,
        roll=roll,
        issues=tuple(issues),
    )


def crop_face(image: np.ndarray, face: DetectedFace, margin: float = 0.25) -> np.ndarray:
    """Return a padded square crop around ``face`` (useful for previews)."""
    x, y, w, h = face.box
    side = max(w, h) * (1.0 + 2.0 * margin)
    cx, cy = x + w / 2.0, y + h / 2.0
    x0 = int(max(0, cx - side / 2.0))
    y0 = int(max(0, cy - side / 2.0))
    x1 = int(min(image.shape[1], cx + side / 2.0))
    y1 = int(min(image.shape[0], cy + side / 2.0))
    if x1 <= x0 or y1 <= y0:
        return np.array(image, copy=True)
    return np.array(image[y0:y1, x0:x1], copy=True)


__all__ = [
    "ARCFACE_TEMPLATE",
    "DetectedFace",
    "QualityReport",
    "FaceDetector",
    "select_face",
    "estimate_alignment",
    "align_face",
    "assess_quality",
    "crop_face",
]
