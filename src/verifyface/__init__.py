"""verifyface — face verification that anyone can use.

Enroll a person once, then verify them from any photo or live camera, on any
platform, fully offline.

    import verifyface as vf

    vf.enroll("kaustav", ["front.jpg", "side.jpg"])   # once
    if vf.verify("kaustav", "new_selfie.jpg"):        # later, anywhere
        print("welcome back, Kaustav")

Everything runs locally: photos never leave the machine, and only a 128-number
template is stored — encrypted and signed.

Developer: Kaustav Kanti Ray
Project:   https://github.com/iamkkronly/verifyface
License:   MIT
"""

from __future__ import annotations

from ._meta import (
    BANNER,
    COPYRIGHT,
    __author__,
    __credit__,
    __developer__,
    __email__,
    __license__,
    __url__,
    __version__,
)
from .config import THRESHOLD_PRESETS, Settings, default_home, default_vault_path
from .engine import CompareResult, Embedding, FaceEngine
from .errors import (
    CameraError,
    ConfigError,
    IdentityExistsError,
    IdentityNotFoundError,
    ImageError,
    LivenessCheckFailed,
    LowQualityError,
    ModelNotFoundError,
    MultipleFacesError,
    NoFaceFoundError,
    StorageError,
    TemplateCorruptedError,
    UnsupportedInputError,
    VerifyFaceError,
)
from .imageio import load_image
from .similarity import describe_score
from .store import StoredProfile, TemplateVault
from .verify import (
    EnrollmentResult,
    IdentifyResult,
    Verifier,
    VerifyResult,
    compare,
    configure,
    enroll,
    get_default,
    identify,
    identities,
    remove,
    same_person,
    verify,
)

__all__ = [
    # metadata
    "__version__",
    "__author__",
    "__developer__",
    "__credit__",
    "__license__",
    "__url__",
    "BANNER",
    "COPYRIGHT",
    # high level API
    "Verifier",
    "enroll",
    "verify",
    "identify",
    "compare",
    "same_person",
    "identities",
    "remove",
    "configure",
    "get_default",
    # results
    "VerifyResult",
    "EnrollmentResult",
    "IdentifyResult",
    "CompareResult",
    "Embedding",
    "StoredProfile",
    # building blocks
    "FaceEngine",
    "TemplateVault",
    "Settings",
    "THRESHOLD_PRESETS",
    "default_home",
    "default_vault_path",
    "load_image",
    "describe_score",
    # errors
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


# --------------------------------------------------------------------------- #
# Optional, slightly heavier helpers are imported lazily so that
# ``import verifyface`` stays fast (≈0.2 s) in serverless environments.
# --------------------------------------------------------------------------- #
_LAZY = {
    "LiveSession": ("verifyface.camera", "LiveSession"),
    "LiveResult": ("verifyface.camera", "LiveResult"),
    "scan_live": ("verifyface.camera", "scan_live"),
    "capture_photo": ("verifyface.camera", "capture_photo"),
    "open_camera": ("verifyface.camera", "open_camera"),
    "liveness": ("verifyface.liveness", None),
    "detect_faces": ("verifyface.preprocess", "FaceDetector"),
    "align_face": ("verifyface.preprocess", "align_face"),
    "crop_face": ("verifyface.preprocess", "crop_face"),
    "assess_quality": ("verifyface.preprocess", "assess_quality"),
    "seal": ("verifyface.security", "seal"),
    "unseal": ("verifyface.security", "unseal"),
}


def __getattr__(name: str):
    """Lazily expose camera / liveness / low-level helpers."""
    if name in _LAZY:
        import importlib

        module_name, attribute = _LAZY[name]
        module = importlib.import_module(module_name)
        value = module if attribute is None else getattr(module, attribute)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(list(globals()) + list(_LAZY))


def credits() -> str:
    """Return the credit banner (used by `verifyface --version`)."""
    return f"{BANNER} · {COPYRIGHT}"
