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
from typing import Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np

from . import _meta
from .config import Settings, resolve_threshold
from .engine import CompareResult, Embedding, FaceEngine
from .errors import (
    ConfigError,
    IdentityExistsError,
    IdentityNotFoundError,
    LivenessCheckFailed,
    NoFaceFoundError,
    TemplateCorruptedError,
)
from .similarity import adaptive_threshold, confidence_from_score, describe_score, resolve_profile
from .store import StoredProfile, TemplateVault

ImageArg = Union[str, bytes, np.ndarray, Path]


def _image_digest(source: object) -> Optional[str]:
    """SHA-256 of the raw bytes when the input is a file or byte string."""
    import hashlib
    import os

    try:
        if isinstance(source, (bytes, bytearray, memoryview)):
            return hashlib.sha256(bytes(source)).hexdigest()
        if isinstance(source, (str, os.PathLike)) and not str(source).lower().startswith(
            ("http://", "https://", "data:", "base64:")
        ):
            path = Path(source).expanduser()
            if path.is_file():
                return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:  # pragma: no cover - never fail verification over a hash
        return None
    return None
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
    # --- 1.1: ambiguity / liveness / second factor ------------------------
    ambiguous: bool = False
    second_best: Optional[Tuple[str, float]] = None
    liveness_status: str = "not_checked"      # not_checked | passed | failed
    replayed_sample: bool = False
    requires_second_factor: bool = False
    second_factor_ok: Optional[bool] = None
    reasons: Tuple[str, ...] = field(default_factory=tuple)

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
            "ambiguous": self.ambiguous,
            "second_best": (
                {"identity": self.second_best[0], "score": round(self.second_best[1], 4)}
                if self.second_best else None
            ),
            "liveness_status": self.liveness_status,
            "replayed_sample": self.replayed_sample,
            "requires_second_factor": self.requires_second_factor,
            "second_factor_ok": self.second_factor_ok,
            "reasons": list(self.reasons),
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
        if self.liveness_status == "failed":
            text += " [liveness check failed — the picture may be a photo of a photo]"
        if self.replayed_sample:
            text += " [this exact file is one of the enrolled photos]"
        if self.ambiguous and self.second_best:
            text += (
                f" [lookalike: {self.second_best[0]!r} scores "
                f"{self.second_best[1]:.3f} too — a second factor is required]"
            )
        if self.requires_second_factor and not self.second_factor_ok:
            text += " [PIN required and not supplied or wrong]"
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
    ambiguous: bool = False
    margin: float = 1.0

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
            "ambiguous": self.ambiguous,
            "margin": round(self.margin, 4),
        }

    def explain(self) -> str:
        if self.ambiguous and self.ranking:
            runner_up = self.ranking[1][0] if len(self.ranking) > 1 else "?"
            return (
                f"Ambiguous: {self.ranking[0][0]!r} and {runner_up!r} look almost identical "
                f"(margin {self.margin:.3f}) — a second factor is required."
            )
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
        profile: Optional[str] = None,
        require_liveness: Optional[bool] = None,
        ambiguity_guard: Optional[bool] = None,
        ambiguity_margin: Optional[float] = None,
        block_replay: Optional[bool] = None,
    ) -> None:
        self.settings = settings or Settings()

        # Named profiles bundle the knobs most people should not have to know.
        presets = {
            "convenience": {
                "threshold": "lenient",
                "require_liveness": False,
                "ambiguity_guard": False,
            },
            "standard": {
                "threshold": "balanced",
                "require_liveness": False,
                "ambiguity_guard": True,
            },
            "high_security": {
                "threshold": "strict",
                "require_liveness": True,
                "ambiguity_guard": True,
                "block_replay": True,
            },
        }
        if profile is not None:
            key = str(profile).strip().lower().replace("-", "_")
            if key not in presets:
                raise ConfigError(
                    f"Unknown profile {profile!r}. Choose one of {', '.join(presets)}."
                )
            chosen = presets[key]
            if threshold is None:
                threshold = chosen["threshold"]
            if require_liveness is None:
                require_liveness = chosen["require_liveness"]
            if ambiguity_guard is None:
                ambiguity_guard = chosen["ambiguity_guard"]
            if block_replay is None:
                block_replay = chosen.get("block_replay", False)
        self.profile_name = str(profile or "standard").strip().lower().replace("-", "_")
        self.require_liveness = bool(require_liveness) if require_liveness is not None else False
        self.ambiguity_guard = True if ambiguity_guard is None else bool(ambiguity_guard)
        self.block_replay = bool(block_replay) if block_replay is not None else False
        self.ambiguity_margin = float(
            ambiguity_margin if ambiguity_margin is not None else self.settings.ambiguity_margin
        )
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
        source_hashes = []
        if self.settings.store_source_hashes:
            for image in images:
                digest = _image_digest(image)
                if digest:
                    source_hashes.append(digest)

        profile = self.vault.save(
            identity,
            vectors,
            qualities=qualities,
            notes=notes,
            max_samples=self.settings.max_samples_per_identity,
            replace=bool(overwrite),
            source_hashes=source_hashes,
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
        pin: Optional[str] = None,
        ambiguity_guard: Optional[bool] = None,
        check_replay: bool = True,
        block_replay: Optional[bool] = None,
    ) -> VerifyResult:
        """Check whether ``image`` shows the person enrolled as ``identity``.

        Beyond the similarity score, four independent guards can refuse a
        verification — each one reports *why* in ``result.reasons``:

        ``liveness``
            ``"auto"`` / ``"required"`` runs the passive anti-spoofing check on
            the probe (a re-photographed screen or print fails it); a
            :class:`~verifyface.liveness.LivenessReport` from a live session is
            used as-is.  ``None`` / ``"off"`` skips the check.
        ``ambiguity_guard``
            Refuses when another enrolled person scores almost as high as
            ``identity`` — the "identical twins / siblings" case.  Defaults to
            the verifier setting.
        ``pin``
            Optional second factor.  When a PIN is set for the identity, a
            missing or wrong PIN can never verify.
        ``check_replay``
            Flags a probe whose file is byte-identical to an enrolled photo
            (an exact replay of a stored image).
        """
        from .liveness import check as liveness_check

        profile = self.vault.load(identity)  # raises if unknown / corrupted
        probe = self.engine.embed(image)

        base_cutoff, name = resolve_profile(threshold, self.threshold)
        cutoff = base_cutoff
        if adaptive and profile.self_similarity:
            cutoff = adaptive_threshold([profile.self_similarity], base_cutoff)

        score = self._match_score(probe, profile)
        matched = bool(score >= cutoff)
        reasons: List[str] = []

        # ---- 1. exact replay of an enrolled file --------------------------
        replayed = False
        if check_replay and profile.source_hashes:
            digest = _image_digest(image)
            if digest is not None and digest in profile.source_hashes:
                replayed = True
                reasons.append(
                    "this exact image is one of the enrolled photos — an uploaded copy "
                    "cannot prove the person is present"
                )

        # ---- 2. liveness --------------------------------------------------
        liveness_status = "not_checked"
        liveness_report: Optional[object] = liveness
        required = self.require_liveness
        if isinstance(liveness, str):
            mode = liveness.strip().lower()
            required = mode in {"auto", "on", "true", "1", "required"}
            liveness_report = None if mode in {"off", "none", "false", "0", ""} else True
        if liveness_report is True or (liveness_report is None and required):
            liveness_report = liveness_check(image)
            required = True
        if liveness_report is not None and hasattr(liveness_report, "passed"):
            liveness_status = "passed" if getattr(liveness_report, "passed", False) else "failed"
            if liveness_status == "failed":
                matched = False
                reasons.extend(getattr(liveness_report, "reasons", ()) or ())
                if not reasons:
                    reasons.append("liveness check failed")

        # ---- 3. lookalike ambiguity --------------------------------------
        guard = self.ambiguity_guard if ambiguity_guard is None else bool(ambiguity_guard)
        second_name, second_score = self._runner_up(probe, exclude=profile.identity)
        ambiguous = bool(
            second_name is not None and (score - second_score) < self.ambiguity_margin
        )

        # ---- 4. second factor --------------------------------------------
        # A correct PIN is *not* a way around the face check: it is exactly what
        # separates two people the face cannot tell apart, so it resolves the
        # ambiguity below instead of being blocked by it.
        requires_pin = bool(profile.has_pin)
        second_ok: Optional[bool] = None
        if requires_pin:
            second_ok = bool(pin is not None and self.check_pin(profile.identity, pin))
            if not second_ok:
                matched = False
                reasons.append(
                    "a PIN is set for this identity — supply pin=… or "
                    "remove it with verifyface clear-pin"
                )

        if ambiguous and guard and not second_ok:
            matched = False
            reasons.append(
                f"{second_name!r} looks almost identical (margin "
                f"{score - second_score:.3f} < {self.ambiguity_margin:.2f}); "
                "set a PIN for this identity or pass ambiguity_guard=False"
            )

        if replayed:
            block = self.block_replay if block_replay is None else bool(block_replay)
            if block:
                matched = False

        result = VerifyResult(
            identity=profile.identity,
            matched=matched,
            score=score,
            threshold=cutoff,
            confidence=confidence_from_score(score, cutoff),
            threshold_name=name,
            quality=probe.quality,
            liveness=liveness_report if hasattr(liveness_report, "passed") else None,
            base_threshold=base_cutoff,
            repaired_template=profile.repaired,
            ambiguous=ambiguous,
            second_best=(second_name, second_score) if second_name else None,
            liveness_status=liveness_status,
            replayed_sample=replayed,
            requires_second_factor=requires_pin,
            second_factor_ok=second_ok,
            reasons=tuple(dict.fromkeys(reasons)),
        )

        if required and liveness_status == "failed" and not matched:
            # explicit request ("required") turns a soft refusal into a hard error
            if isinstance(liveness, str) and liveness.strip().lower() == "required":
                raise LivenessCheckFailed(result.explain())

        return result

    # -- helpers for the guards ------------------------------------------- #
    def _runner_up(self, probe: Embedding, *, exclude: str) -> Tuple[Optional[str], float]:
        """Best *other* enrolled identity (empty when nobody else is enrolled)."""
        best_name: Optional[str] = None
        best_score = -1.0
        for name in self.vault.identities():
            if name == exclude:
                continue
            try:
                other = self.vault.load(name)
            except Exception:
                continue
            score = self._match_score(probe, other)
            if score > best_score:
                best_name, best_score = other.identity, score
        if best_name is None:
            return None, 0.0
        return best_name, float(best_score)

    def lookalikes(self, threshold: float = 0.5) -> List[Tuple[str, str, float]]:
        """Enrolled pairs that are too similar to be told apart reliably.

        Identical twins, siblings and very close lookalikes will show up here.
        The right response is a second factor (a PIN), not a higher threshold.
        """
        names = self.vault.identities()
        pairs: List[Tuple[str, str, float]] = []
        for i, first in enumerate(names):
            try:
                a = self.vault.load(first)
            except Exception:
                continue
            for second in names[i + 1:]:
                try:
                    b = self.vault.load(second)
                except Exception:
                    continue
                pair_score = max(
                    self.engine.similarity(a.centroid, b.centroid),
                    max(
                        (self.engine.similarity(s, b.centroid) for s in a.samples),
                        default=-1.0,
                    ),
                )
                if pair_score >= threshold:
                    pairs.append((a.identity, b.identity, float(pair_score)))
        pairs.sort(key=lambda item: item[2], reverse=True)
        return pairs

    # -- second factor ------------------------------------------------------ #
    def set_pin(self, identity: str, pin: str) -> None:
        """Attach a PIN / passphrase to an enrolled identity."""
        from .security import hash_pin, validate_pin

        validate_pin(pin)
        self.vault.update_fields(identity, pin=hash_pin(pin))

    def clear_pin(self, identity: str) -> None:
        """Remove the PIN from an identity."""
        self.vault.update_fields(identity, pin="")

    def has_pin(self, identity: str) -> bool:
        return bool(self.vault.load(identity).has_pin)

    def check_pin(self, identity: str, pin: Optional[str]) -> bool:
        """Constant-time check of a PIN without revealing whether it exists."""
        from .security import verify_pin as _verify

        if not pin:
            return False
        try:
            record = self.vault.load(identity)
        except (IdentityNotFoundError, TemplateCorruptedError):
            return False
        if not record.has_pin:
            return False
        payload = self.vault.load_payload(identity)
        return _verify(pin, str(payload.get("pin", "")))

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
            # ranking is by raw similarity; the adaptive relax only matters for the
            # final yes/no decision below, never for the ordering of candidates
            ranking.append((profile.identity, self._match_score(probe, profile)))
        ranking.sort(key=lambda item: item[1], reverse=True)

        best_name, best_score = (ranking[0] if ranking else (None, 0.0))
        margin = 1.0
        ambiguous = False
        if len(ranking) > 1:
            margin = float(best_score - ranking[1][1])
            ambiguous = margin < self.ambiguity_margin
        matched = bool(best_name is not None and best_score >= cutoff)
        if ambiguous and self.ambiguity_guard:
            matched = False
        return IdentifyResult(
            identity=best_name if matched else None,
            matched=matched,
            score=float(best_score),
            threshold=cutoff,
            confidence=confidence_from_score(float(best_score), cutoff),
            ranking=ranking[:10],
            quality=probe.quality,
            ambiguous=ambiguous,
            margin=margin,
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
            "profile": self.profile_name,
            "require_liveness": self.require_liveness,
            "ambiguity_guard": self.ambiguity_guard,
            "ambiguity_margin": self.ambiguity_margin,
            "block_replay": self.block_replay,
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
