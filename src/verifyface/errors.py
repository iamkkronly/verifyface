"""Exception hierarchy for verifyface.

Every error raised on purpose by this library inherits from
:class:`VerifyFaceError`, so a caller can catch one type and still be safe.
Messages are written to be shown directly to a human user.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations


class VerifyFaceError(Exception):
    """Base class for every verifyface error."""

    #: Short, human friendly hint appended to the message by the CLI.
    hint: str = ""

    def __init__(self, message: str, *, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        if hint:
            self.hint = hint

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.hint:
            return f"{self.message}\nHint: {self.hint}"
        return self.message


class ConfigError(VerifyFaceError):
    """A configuration value (path, threshold name, option) is invalid."""


class ModelNotFoundError(VerifyFaceError):
    """The face models could not be located on this machine."""

    hint = (
        "Run `python -m verifyface download-models` once while online, or set "
        "VERIFYFACE_MODEL_DIR to a folder that contains the .onnx files."
    )


class ImageError(VerifyFaceError):
    """The input could not be read as an image (unreadable, corrupt, empty)."""


class UnsupportedInputError(ImageError):
    """The input type is not something verifyface knows how to read."""


class NoFaceFoundError(VerifyFaceError):
    """No face was detected in the picture."""

    hint = (
        "Use a clear, front-facing photo where the face is at least ~80x80 pixels, "
        "well lit and not covered."
    )


class MultipleFacesError(VerifyFaceError):
    """More than one face was found and the caller asked for a strict single face."""

    hint = "Crop the photo to one person, or pass mode='largest' to pick the biggest face."


class LowQualityError(VerifyFaceError):
    """The face was found but is too blurry / dark / tilted to be verified safely."""

    hint = "Move closer to a light source, hold still, and take the photo again."


class IdentityNotFoundError(VerifyFaceError):
    """There is no enrolled profile for the requested name."""

    hint = "Enroll the person first: verifyface.enroll('name', 'photo.jpg')."


class IdentityExistsError(VerifyFaceError):
    """The name is already enrolled and ``overwrite`` was not requested."""

    hint = "Pass overwrite=True to replace the existing profile."


class TemplateCorruptedError(VerifyFaceError):
    """A stored template failed its integrity check (bit rot, edit or disk error)."""

    hint = (
        "verifyface auto-repairs from the last good backup when possible. If this keeps "
        "happening, enroll the person again — the original photo is never needed."
    )


class LivenessCheckFailed(VerifyFaceError):
    """The anti-spoofing / challenge-response check did not pass."""

    hint = "Use a live camera and follow the on-screen prompts."


class CameraError(VerifyFaceError):
    """No usable camera, or the camera was closed by the user."""

    hint = "Check that a webcam is connected and not in use by another app."


class StorageError(VerifyFaceError):
    """The vault directory could not be created, read or written."""


__all__ = [
    "VerifyFaceError",
    "ConfigError",
    "ModelNotFoundError",
    "ImageError",
    "UnsupportedInputError",
    "NoFaceFoundError",
    "MultipleFacesError",
    "LowQualityError",
    "IdentityNotFoundError",
    "IdentityExistsError",
    "TemplateCorruptedError",
    "LivenessCheckFailed",
    "CameraError",
    "StorageError",
]
