"""The friendly, high-level API.

Almost everybody only needs four functions::

    import verifyface as vf

    vf.enroll("kaustav", "photo1.jpg")          # once
    vf.verify("kaustav", "selfie.jpg")          # any time, anywhere
    vf.identify("group_or_selfie.jpg")          # who is this?
    vf.compare("before.jpg", "after.jpg")       # are these the same person?

The :class:`Verifier` class exposes the same features when you need your own
vault, your own threshold or several independent tenants.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np

from . import _meta
from .config import Settings, default_vault_path, resolve_threshold
from .engine import CompareResult, Embedding, FaceEngine
from .errors import (
    IdentityExistsError,
    IdentityNotFoundError,
    NoFaceFoundError,
    TemplateCorruptedError,
)
from .similarity import adaptive_threshold, confidence_from_score, describe_score, resolve_profile
from .store import StoredProfile, TemplateVault

ImageArg = Union[str, bytes, np.ndarray, Path]
ImageList = Union[ImageArg, Sequence[ImageArg]]


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
@dataclass
class EnrollmentResult:
    """What happened when a person was enrolled."""

    identity: str
    samples: int
    self_similarity: float
    quality: float
    created: bool
    duplicates_skipped: int = 0
    skipped_images: List[str] = field(default_factory=list)
    vault: str = ""

    def __bool__(self) -> bool:
        return self.samples > 0

    def as_dict(self) -> dict:
        return {
            "identity": self.identity,
            "samples": self.samples,
            "self_similarity": round(self.self_similarity, 4),
            "quality": round(self.quality, 4),
            "created": self.created,
            "duplicates_skipped": self.duplicates_skipped,
            "skipped_images": self.skipped_images,
            "vault": self.vault,
        }

    def explain(self) -> str:
        verb = "enrolled" if self.created else "updated"
        text = (
            f"{verb} {self.identity!r} with {self.samples} face sample(s) "
            f"(self-consistency {self.self_similarity:.2f}, quality {self.quality:.2f})"
        )
        if self.duplicates_skipped:
            text += f", {self.duplicates_skipped} duplicate photo(s) skipped"
        if self.skipped_images:
            text += f", {len(self.skipped_images)} image(s) without a usable face ignored"
        return text + "."


@dataclass
class VerifyResult:
    """The outcome of a verification.  Truthy when the person matched."""

    identity: str
    matched: bool
    score: float
    threshold: float
    confidence: float
    threshold_name: str = "balanced"
    quality: Optional[object] = None
    liveness: Optional[object] = None
    base_threshold: Optional[float] = None
    repaired_template: bool = False
    notes: Tuple[str, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        return self.matched

    def as_dict(self) -> dict:
        return {
            "identity": self.identity,
            "matched": self.matched,
            "score": round(self.score, 4),
            "threshold": round(self.threshold, 4),
            "base_threshold": round(self.base_threshold, 4) if self.base_threshold else None,
            "confidence": round(self.confidence, 4),
            "threshold_name": self.threshold_name,
            "quality": self.quality.as_dict() if hasattr(self.quality, "as_dict") else None,
            "liveness": self.liveness.as_dict() if hasattr(self.liveness, "as_dict") else None,
            "repaired_template": self.repaired_template,
            "notes": list(self.notes),
            "developer": _meta.__author__,
        }

    def explain(self) -> str:
        verdict = "VERIFIED" if self.matched else "NOT verified"
        text = (
            f"{verdict}: {self.identity!r} — similarity {self.score:.3f} "
            f"(threshold {self.threshold:.3f}, {self.confidence * 100:.1f}% confidence, "
            f"{describe_score(self.score)})"
        )
        if self.repaired_template:
            text += " [template auto-repaired from backup]"
        return text


@dataclass
class IdentifyResult:
    """Best match for a probe photo among all enrolled people."""

    identity: Optional[str]
    matched: bool
    score: float
    threshold: float
    confidence: float
    ranking: List[Tuple[str, float]] = field(default_factory=list)
    quality: Optional[object] = None

    def __bool__(self) -> bool:
        return self.matched

    def as_dict(self) -> dict:
        return {
            "identity": self.identity,
            "matched": self.matched,
            "score": round(self.score, 4),
            "threshold": round(self.threshold, 4),
            "confidence": round(self.confidence, 4),
            "ranking": [(name, round(s, 4)) for name, s in self.ranking],
            "quality": self.quality.as_dict() if hasattr(self.quality, "as_dict") else None,
        }

    def explain(self) -> str:
        if self.matched:
            return f"Identified as {self.identity!r} (similarity {self.score:.3f})."
        if self.ranking:
            return (
                "No enrolled person matched "
                f"(closest: {self.ranking[0][0]!r} at {self.ranking[0][1]:.3f} < "
                f"{self.threshold:.3f})."
            )
        return "No enrolled people to compare against."


# --------------------------------------------------------------------------- #
# Verifier
# --------------------------------------------------------------------------- #
class Verifier:
    """A verification service bound to one vault and one threshold policy.

    Example
    -------
    >>> import verifyface as vf
    >>> v = vf.Verifier(threshold="strict")
    >>> v.enroll("kaustav", ["front.jpg", "left.jpg"])
    >>> bool(v.verify("kaustav", "new_selfie.jpg"))
    True
    """

    def __init__(
        self,
        *,
        vault: Optional[Union[str, Path]] = None,
        threshold: Union[str, float, None] = None,
        model_dir: Optional[Union[str, Path]] = None,
        allow_download: bool = True,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or Settings()
        if vault is not None:
            self.settings.vault = Path(vault).expanduser()
        if model_dir is not None:
            self.settings.model_dir = Path(model_dir).expanduser()
        self.settings.allow_download = allow_download
        self.threshold = resolve_threshold(threshold if threshold is not None else self.settings.threshold)
        self.threshold_name = (
            threshold if isinstance(threshold, str) else resolve_profile(None, self.threshold)[1]
        )
        self.vault = TemplateVault(self.settings.vault, auto_repair=self.settings.auto_repair)
        self._engine: Optional[FaceEngine] = None
        self._lock = threading.RLock()

    # -- engine ------------------------------------------------------------ #
    @property
    def engine(self) -> FaceEngine:
        if self._engine is None:
            with self._lock:
                if self._engine is None:
                    self._engine = FaceEngine(
                        settings=self.settings,
                        model_dir=self.settings.model_dir,
                        detection_confidence=self.settings.detection_confidence,
                    )
        return self._engine

    # -- enrollment --------------------------------------------------------- #
    def enroll(
        self,
        identity: str,
        images: ImageList,
        *,
        overwrite: bool = False,
        notes: str = "",
        add: bool = True,
        dedupe_threshold: float = 0.985,
    ) -> EnrollmentResult:
        """Register a person from one or more photos.

        Two or three photos taken on different days (with and without glasses,
        different hairstyle) make verification noticeably more robust later —
        but a single clear photo already works.

        Parameters
        ----------
        identity
            Any name, including unicode (``"কৌস্তভ"``).
        images
            One image source or a list of them.
        overwrite
            Replace the existing profile instead of adding to it.
        add
            When ``False``, behaves like ``overwrite=True``.
        """
        identity = str(identity).strip()
        if not identity:
            raise ValueError("Identity name must not be empty.")

        if not isinstance(images, (list, tuple)):
            images = [images]
        if not images:
            raise ValueError("enroll() needs at least one image.")

        existing = self.vault.contains(identity)
        if existing and not (overwrite or add):
            raise IdentityExistsError(
                f"{identity!r} is already enrolled.",
                hint="Use overwrite=True to replace, or add more photos deliberately.",
            )

        embeddings: List[Embedding] = []
        skipped: List[str] = []
        for image in images:
            try:
                embeddings.append(self.engine.embed(image, strict_quality=False))
            except NoFaceFoundError:
                skipped.append(str(image) if isinstance(image, (str, Path)) else "image")
        if not embeddings:
            raise NoFaceFoundError(
                "None of the supplied images contained a usable face. "
                "Use a clear, well lit photo where the face fills a good part of the frame."
            )

        # Drop near-identical samples so a burst of selfies does not dominate.
        unique: List[Embedding] = []
        duplicates = 0
        for candidate in embeddings:
            if any(
                self.engine.similarity(candidate.vector, kept.vector) >= dedupe_threshold
                for kept in unique
            ):
                duplicates += 1
                continue
            unique.append(candidate)

        vectors = [e.vector for e in unique]
        qualities = [e.quality.score for e in unique]
        profile = self.vault.save(
            identity,
            vectors,
            qualities=qualities,
            notes=notes,
            max_samples=self.settings.max_samples_per_identity,
            replace=bool(overwrite),
        )
        return EnrollmentResult(
            identity=identity,
            samples=profile.sample_count,
            self_similarity=profile.self_similarity,
            quality=float(sum(qualities) / len(qualities)),
            created=not existing,
            duplicates_skipped=duplicates,
            skipped_images=skipped,
            vault=str(self.vault.path),
        )

    # -- verification -------------------------------------------------------- #
    def _match_score(self, probe: Embedding, profile: StoredProfile) -> float:
        """Blend centroid and best-sample similarity (robust + forgiving)."""
        centroid_score = self.engine.similarity(probe.vector, profile.centroid)
        sample_score = max(
            (self.engine.similarity(probe.vector, sample) for sample in profile.samples),
            default=centroid_score,
        )
        return float(0.7 * centroid_score + 0.3 * sample_score)

    def verify(
        self,
        identity: str,
        image: ImageArg,
        *,
        threshold: Union[str, float, None] = None,
        adaptive: bool = True,
        liveness: Optional[object] = None,
    ) -> VerifyResult:
        """Check whether ``image`` shows the person enrolled as ``identity``."""
        profile = self.vault.load(identity)  # raises if unknown / corrupted
        probe = self.engine.embed(image)

        base_cutoff, name = resolve_profile(
            threshold, self.threshold if threshold is None else self.threshold
        )
        cutoff = base_cutoff
        if adaptive and profile.self_similarity:
            cutoff = adaptive_threshold([profile.self_similarity], base_cutoff)

        score = self._match_score(probe, profile)
        matched = bool(score >= cutoff)
        if liveness is not None and getattr(liveness, "passed", True) is False:
            matched = False

        return VerifyResult(
            identity=profile.identity,
            matched=matched,
            score=score,
            threshold=cutoff,
            confidence=confidence_from_score(score, cutoff),
            threshold_name=name,
            quality=probe.quality,
            liveness=liveness,
            base_threshold=base_cutoff,
            repaired_template=profile.repaired,
        )

    def verify_any(
        self,
        image: ImageArg,
        candidates: Optional[Iterable[str]] = None,
        **kwargs,
    ) -> IdentifyResult:
        """Alias of :meth:`identify` with clearer intent for "is it anyone?"."""
        return self.identify(image, candidates=candidates, **kwargs)

    def identify(
        self,
        image: ImageArg,
        *,
        candidates: Optional[Iterable[str]] = None,
        threshold: Union[str, float, None] = None,
        adaptive: bool = True,
    ) -> IdentifyResult:
        """Find out *who* is in the photo, by comparing against every profile."""
        cutoff, _ = resolve_profile(threshold, self.threshold)
        names = list(candidates) if candidates is not None else self.vault.identities()
        if not names:
            raise IdentityNotFoundError(
                "Nobody is enrolled yet, so there is nothing to identify.",
                hint="Enroll at least one person first.",
            )

        probe = self.engine.embed(image)
        ranking: List[Tuple[str, float]] = []
        for name in names:
            try:
                profile = self.vault.load(name)
            except (TemplateCorruptedError, IdentityNotFoundError):
                continue
            local_cutoff = (
                adaptive_threshold([profile.self_similarity], cutoff) if adaptive else cutoff
            )
            ranking.append((profile.identity, self._match_score(probe, profile)))
        ranking.sort(key=lambda item: item[1], reverse=True)

        best_name, best_score = (ranking[0] if ranking else (None, 0.0))
        matched = bool(best_name is not None and best_score >= cutoff)
        return IdentifyResult(
            identity=best_name if matched else None,
            matched=matched,
            score=float(best_score),
            threshold=cutoff,
            confidence=confidence_from_score(float(best_score), cutoff),
            ranking=ranking[:10],
            quality=probe.quality,
        )

    def compare(
        self, image_a: ImageArg, image_b: ImageArg, *, threshold: Union[str, float, None] = None
    ) -> CompareResult:
        """Compare two photos without storing anything."""
        return self.engine.compare(image_a, image_b, threshold=threshold or self.threshold)

    # -- profile management -------------------------------------------------- #
    def enrolled(self, identity: str) -> bool:
        return self.vault.contains(identity)

    __contains__ = enrolled

    def identities(self) -> List[str]:
        return self.vault.identities()

    def profile(self, identity: str) -> StoredProfile:
        return self.vault.load(identity)

    def remove(self, identity: str) -> bool:
        return self.vault.delete(identity)

    # ``delete`` reads nicer for many people than ``remove``
    delete = remove

    def info(self) -> dict:
        return {
            "developer": _meta.__author__,
            "version": _meta.__version__,
            "vault": str(self.vault.path),
            "threshold": self.threshold,
            "threshold_name": self.threshold_name,
            "identities": len(self.vault.identities()),
            "engine": self.engine.info(),
        }


# --------------------------------------------------------------------------- #
# Module level singleton API
# --------------------------------------------------------------------------- #
_default: Optional[Verifier] = None
_default_lock = threading.Lock()


def get_default() -> Verifier:
    """Return the process-wide default :class:`Verifier` (created on demand)."""
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = Verifier()
    return _default


def configure(
    *,
    vault: Optional[Union[str, Path]] = None,
    threshold: Union[str, float, None] = None,
    model_dir: Optional[Union[str, Path]] = None,
    allow_download: bool = True,
) -> Verifier:
    """Re-create the default verifier with new settings (e.g. a project vault)."""
    global _default
    with _default_lock:
        _default = Verifier(
            vault=vault,
            threshold=threshold,
            model_dir=model_dir,
            allow_download=allow_download,
        )
    return _default


def enroll(identity: str, images: ImageList, **kwargs) -> EnrollmentResult:
    """Enroll ``identity`` using one or more photos (module-level shortcut)."""
    return get_default().enroll(identity, images, **kwargs)


def verify(identity: str, image: ImageArg, **kwargs) -> VerifyResult:
    """Verify a photo against an enrolled identity (module-level shortcut)."""
    return get_default().verify(identity, image, **kwargs)


def identify(image: ImageArg, **kwargs) -> IdentifyResult:
    """Find the enrolled person in ``image`` (module-level shortcut)."""
    return get_default().identify(image, **kwargs)


def compare(image_a: ImageArg, image_b: ImageArg, **kwargs) -> CompareResult:
    """Compare two photos (module-level shortcut, stores nothing)."""
    return get_default().compare(image_a, image_b, **kwargs)


def same_person(image_a: ImageArg, image_b: ImageArg, **kwargs) -> bool:
    """Convenience: ``True`` when both photos show the same person."""
    return bool(compare(image_a, image_b, **kwargs))


def identities() -> List[str]:
    """Every enrolled identity in the default vault."""
    return get_default().identities()


def remove(identity: str) -> bool:
    """Delete an enrolled identity (module-level shortcut)."""
    return get_default().remove(identity)


__all__ = [
    "Verifier",
    "VerifyResult",
    "EnrollmentResult",
    "IdentifyResult",
    "get_default",
    "configure",
    "enroll",
    "verify",
    "identify",
    "compare",
    "same_person",
    "identities",
    "remove",
]
