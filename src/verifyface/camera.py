"""Live camera scanning and the framework-agnostic :class:`LiveSession`.

Two ways to do a *live* verification:

``scan_live()``
    Desktop one-call helper: opens the webcam, draws the instructions, runs the
    challenges and returns the result.  Needs ``opencv-python`` (not the
    headless build) for the on-screen window.

``LiveSession``
    A tiny state machine that accepts frames from *anywhere* — a Flask route,
    a FastAPI upload, a Gradio webcam widget, a phone browser, a Raspberry Pi.
    The server never needs a camera, which is what makes live verification work
    on every platform.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .errors import CameraError, LowQualityError, MultipleFacesError, NoFaceFoundError
from .imageio import encode_jpeg, load_image
from .liveness import LivenessReport, LivenessTracker, passive_check, random_actions
from .preprocess import align_face, assess_quality, select_face


# --------------------------------------------------------------------------- #
# Camera plumbing
# --------------------------------------------------------------------------- #
def _camera_backend(cv2) -> int:
    import sys

    if sys.platform.startswith("win"):
        return cv2.CAP_DSHOW      # far faster to open on Windows
    if sys.platform == "darwin":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_ANY


def open_camera(index: int = 0, *, width: int = 640, height: int = 480):
    """Open a webcam and return the OpenCV ``VideoCapture``."""
    import cv2

    capture = cv2.VideoCapture(index, _camera_backend(cv2))
    if not capture.isOpened():
        capture.release()
        capture = cv2.VideoCapture(index)  # retry with the default backend
    if not capture.isOpened():
        raise CameraError(
            f"Could not open camera #{index}.",
            hint="Close other apps that may be using it, or try another index: scan_live(camera=1).",
        )
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return capture


def read_frame(capture) -> np.ndarray:
    """Read one frame from an open capture, raising a helpful error on failure."""
    ok, frame = capture.read()
    if not ok or frame is None:
        raise CameraError("The camera returned an empty frame.", hint="Reconnect the camera.")
    return frame


def has_gui() -> bool:
    """True when this OpenCV build can open an on-screen window."""
    import cv2

    return hasattr(cv2, "imshow") and hasattr(cv2, "waitKey")


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
@dataclass
class LiveResult:
    """Outcome of a live capture session."""

    passed: bool
    liveness: LivenessReport
    frames: int = 0
    verify: Optional[Any] = None       # VerifyResult, when an identity was supplied
    enrolled: Optional[Any] = None     # EnrollmentResult, in enroll mode
    best_frame: Optional[np.ndarray] = None
    preview_jpeg: Optional[bytes] = None
    message: str = ""

    def __bool__(self) -> bool:
        return self.passed

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "liveness": self.liveness.as_dict(),
            "frames": self.frames,
            "verify": self.verify.as_dict() if hasattr(self.verify, "as_dict") else None,
            "enrolled": self.enrolled.as_dict() if hasattr(self.enrolled, "as_dict") else None,
            "message": self.message,
        }


# --------------------------------------------------------------------------- #
# Framework agnostic live session
# --------------------------------------------------------------------------- #
class LiveSession:
    """State machine for a live scan fed by frames from any client.

    Example (Flask/FastAPI/Gradio/browser — anywhere)::

        session = verifyface.LiveSession(identity="kaustav")
        state = session.begin()
        while state["status"] != "done":
            state = session.feed(frame_bytes)   # JPEG/PNG bytes or a numpy array

    ``state`` always contains ``status`` (``prompt`` / ``done`` / ``error``),
    ``prompt`` (text for the user), ``progress`` (0..1) and ``passed``.
    """

    def __init__(
        self,
        *,
        identity: Optional[str] = None,
        verifier: Optional[Any] = None,
        mode: str = "verify",
        actions: int = 2,
        challenge_pool: Optional[Sequence[str]] = None,
        require_liveness: bool = True,
        passive_threshold: float = 0.35,
        frame_budget: int = 120,
        notes: str = "",
    ) -> None:
        if mode not in {"verify", "enroll", "capture"}:
            raise ValueError("mode must be 'verify', 'enroll' or 'capture'")
        if mode in {"verify", "enroll"} and not identity:
            raise ValueError(f"mode={mode!r} needs an identity name")

        self.identity = identity
        self.mode = mode
        self.verifier = verifier
        self.notes = notes
        self.require_liveness = bool(require_liveness) and actions > 0
        self.passive_threshold = passive_threshold
        self.challenges = random_actions(actions, challenge_pool) if actions else ()
        self.tracker = LivenessTracker(self.challenges, frame_budget=frame_budget)
        self.frames = 0
        self.best_frame: Optional[np.ndarray] = None
        self.best_quality = -1.0
        self.result: Optional[LiveResult] = None
        self.message = ""
        self._error: Optional[str] = None

    # -- helpers ------------------------------------------------------------ #
    def _state(self, status: str, prompt: str, **extra) -> Dict[str, Any]:
        payload = {
            "status": status,
            "prompt": prompt,
            "progress": round(self.tracker.progress, 3),
            "actions_required": list(self.tracker.actions),
            "actions_completed": list(self.tracker.completed),
            "frames": self.frames,
            "passed": bool(self.result.passed) if self.result else False,
            "developer": "Kaustav Kanti Ray",
        }
        payload.update(extra)
        return payload

    def _engine(self):
        from .verify import get_default

        verifier = self.verifier or get_default()
        return verifier, verifier.engine

    # -- lifecycle ----------------------------------------------------------- #
    def begin(self) -> Dict[str, Any]:
        """Start the session and return the first prompt for the user."""
        first = self.tracker.prompt
        return self._state("prompt", first, session_started=True)

    def feed(self, frame) -> Dict[str, Any]:
        """Push one frame (bytes / numpy / path) and get the next state."""
        if self.result is not None:
            return self._state("done", self.result.message or "Completed")
        if self._error:
            return self._state("error", self._error)

        self.frames += 1
        try:
            pixels = load_image(frame)
        except Exception as exc:
            self._error = f"Could not read that frame: {exc}"
            return self._state("error", self._error)

        verifier, engine = self._engine()

        # 1. exactly one person --------------------------------------------------
        try:
            faces = engine.detector.detect(pixels)
            if not faces:
                return self._state("prompt", "No face detected — center your face in the frame")
            if len(faces) > 1:
                return self._state("prompt", "More than one face — please be alone in the frame")
            face = select_face(faces, mode="strict", min_size=engine.settings.min_face_size)
        except MultipleFacesError:
            return self._state("prompt", "More than one face — please be alone in the frame")
        except (NoFaceFoundError, LowQualityError) as exc:
            return self._state("prompt", str(exc).split("\n")[0])

        aligned = align_face(pixels, face, 112)
        quality = assess_quality(
            pixels,
            face,
            aligned,
            min_sharpness=engine.settings.min_sharpness,
            min_brightness=engine.settings.min_brightness,
            max_brightness=engine.settings.max_brightness,
            max_yaw=engine.settings.max_yaw_degrees,
            max_roll=engine.settings.max_roll_degrees,
        )
        if not quality.passed:
            # keep the best frame anyway, the person may just be moving
            pass
        elif quality.score > self.best_quality:
            self.best_quality = quality.score
            self.best_frame = np.array(pixels, copy=True)

        # 2. challenges ----------------------------------------------------------
        if self.require_liveness:
            self.tracker.update(pixels, face)

        if self.require_liveness and self.tracker.pending:
            if self.tracker.frames >= self.tracker.frame_budget:
                self.result = LiveResult(
                    passed=False,
                    liveness=self.tracker.report(reasons=("time limit reached",)),
                    frames=self.frames,
                    best_frame=self.best_frame,
                    message="Liveness check timed out — please try again.",
                )
                return self._state("done", self.result.message)
            return self._state("prompt", self.tracker.prompt)

        # 3. passive anti-spoofing on the best frame -----------------------------
        reference = self.best_frame if self.best_frame is not None else pixels
        passive_score, reasons = passive_check(reference, threshold=self.passive_threshold)
        liveness = self.tracker.report(passive_score=passive_score, reasons=reasons)
        if self.require_liveness and liveness.passed and passive_score < self.passive_threshold:
            liveness.passed = False
            liveness.reasons = tuple(reasons) + ("looks like a screen or a printed photo",)

        # 4. finish --------------------------------------------------------------
        if self.require_liveness and not liveness.passed:
            self.result = LiveResult(
                passed=False,
                liveness=liveness,
                frames=self.frames,
                best_frame=self.best_frame,
                message=liveness.explain(),
            )
            return self._state("done", self.result.message)

        preview = encode_jpeg(reference, 80) if reference is not None else None
        try:
            if self.mode == "verify":
                verification = verifier.verify(self.identity, reference, liveness=liveness)
                passed = bool(verification.matched)
                message = verification.explain()
                self.result = LiveResult(
                    passed=passed,
                    liveness=liveness,
                    frames=self.frames,
                    verify=verification,
                    best_frame=reference,
                    preview_jpeg=preview,
                    message=message,
                )
            elif self.mode == "enroll":
                enrollment = verifier.enroll(
                    self.identity, [reference], notes=self.notes or "enrolled via live scan"
                )
                self.result = LiveResult(
                    passed=True,
                    liveness=liveness,
                    frames=self.frames,
                    enrolled=enrollment,
                    best_frame=reference,
                    preview_jpeg=preview,
                    message=enrollment.explain(),
                )
            else:  # capture
                self.result = LiveResult(
                    passed=True,
                    liveness=liveness,
                    frames=self.frames,
                    best_frame=reference,
                    preview_jpeg=preview,
                    message="Live face captured.",
                )
        except Exception as exc:  # surface library errors as state, never crash a server
            self.result = LiveResult(
                passed=False,
                liveness=liveness,
                frames=self.frames,
                best_frame=reference,
                message=str(exc),
            )
            return self._state("done", self.result.message)

        return self._state("done", self.result.message)

    # -- serialisation for web clients --------------------------------------- #
    def preview_data_uri(self) -> Optional[str]:
        if self.result is None or not self.result.preview_jpeg:
            return None
        import base64

        return "data:image/jpeg;base64," + base64.b64encode(self.result.preview_jpeg).decode()


# --------------------------------------------------------------------------- #
# Desktop helper
# --------------------------------------------------------------------------- #
def scan_live(
    identity: Optional[str] = None,
    *,
    mode: str = "verify",
    camera: int = 0,
    verifier: Optional[Any] = None,
    actions: int = 2,
    preview: bool = True,
    mirror: bool = True,
    timeout: float = 30.0,
    window_name: str = "verifyface — Developer: Kaustav Kanti Ray",
) -> LiveResult:
    """Open the webcam and run a complete live scan on the desktop.

    Returns a :class:`LiveResult`; press ``q`` or ``Esc`` to cancel.
    """
    import cv2

    session = LiveSession(
        identity=identity, verifier=verifier, mode=mode, actions=actions
    )
    capture = open_camera(camera)
    gui = preview and has_gui()
    started = time.time()
    state = session.begin()

    try:
        while True:
            frame = read_frame(capture)
            if mirror:
                frame = cv2.flip(frame, 1)
            state = session.feed(frame)

            if gui:
                display = frame.copy()
                colour = (0, 200, 0) if state["status"] == "done" else (60, 180, 255)
                cv2.rectangle(display, (0, 0), (display.shape[1], 58), (20, 20, 20), -1)
                cv2.putText(
                    display, state["prompt"][:60], (12, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, colour, 2, cv2.LINE_AA,
                )
                cv2.putText(
                    display,
                    f"verifyface • Developer: Kaustav Kanti Ray",
                    (12, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (170, 170, 170), 1, cv2.LINE_AA,
                )
                cv2.imshow(window_name, display)
                if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                    break
            else:
                time.sleep(0.01)

            if state["status"] in {"done", "error"}:
                if gui:
                    cv2.waitKey(600)
                break
            if time.time() - started > timeout:
                break
    finally:
        capture.release()
        if gui:
            try:
                cv2.destroyAllWindows()
            except Exception:  # pragma: no cover
                pass

    if session.result is not None:
        return session.result
    report = session.tracker.report(reasons=("session cancelled or timed out",))
    return LiveResult(
        passed=False,
        liveness=report,
        frames=session.frames,
        message="Live scan did not complete.",
    )


def capture_photo(camera: int = 0, *, warmup: int = 5, mirror: bool = True) -> np.ndarray:
    """Grab a single still from the webcam (handy for enrollment from a kiosk)."""
    import cv2

    capture = open_camera(camera)
    try:
        frame = None
        for _ in range(max(1, warmup)):  # let exposure settle
            frame = read_frame(capture)
        if frame is None:  # pragma: no cover
            raise CameraError("The camera produced no frames.")
        return cv2.flip(frame, 1) if mirror else frame
    finally:
        capture.release()


__all__ = [
    "LiveSession",
    "LiveResult",
    "scan_live",
    "capture_photo",
    "open_camera",
    "read_frame",
    "has_gui",
]
