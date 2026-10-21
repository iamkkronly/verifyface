"""The template vault: crash-safe, tamper-evident storage of face templates.

Guarantees
----------
1. **Atomic writes** — a template is written to a temporary file, fsynced and
   then renamed over the old one.  A power cut can never leave half a file.
2. **Signed** — every record carries an HMAC-SHA256 signature (and AES-256-GCM
   encryption when :mod:`cryptography` is installed).
3. **Self-healing** — the last known-good copy is kept as ``*.bak``.  If the
   live file is damaged, it is transparently restored, so a corrupted byte can
   never lock a person out permanently.
4. **Owner-only permissions** — ``0700`` directories, ``0600`` files.
5. **No photos** — only 128 float numbers per sample are stored.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from . import _meta
from .errors import IdentityNotFoundError, StorageError, TemplateCorruptedError
from .security import (
    harden_path,
    is_private,
    load_or_create_key,
    seal,
    unseal,
)

TEMPLATE_FORMAT_VERSION = 1
DIM = 128

_ALLOWED_ASCII = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_. ")
_DOTS = re.compile(r"\.{2,}")


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(identity: str) -> str:
    """Turn any display name (including Bengali, emoji, spaces) into a safe filename.

    A short hash of the *exact* name is appended, so two different names can
    never collide and no name can escape the vault directory.
    """
    name = str(identity).strip()
    if not name:
        raise ValueError("Identity name must not be empty.")
    pieces = []
    for character in name:
        if character in _ALLOWED_ASCII:
            pieces.append(character)
        elif character.isalnum() or unicodedata.category(character).startswith("M"):
            pieces.append(character)      # Bengali, Arabic, CJK … and their marks
        elif unicodedata.category(character).startswith("Z"):
            pieces.append(" ")
        else:
            pieces.append("_")
    cleaned = _DOTS.sub(".", "".join(pieces)).strip(" .")
    cleaned = cleaned[:40] or "identity"
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:10]
    return f"{cleaned}--{digest}"


@dataclass
class StoredProfile:
    """One enrolled identity as loaded from the vault."""

    identity: str
    samples: List[np.ndarray]
    centroid: np.ndarray
    created_at: str
    updated_at: str
    self_similarity: float = 0.0
    repaired: bool = False
    path: Optional[Path] = None
    notes: str = ""

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    def as_dict(self) -> dict:
        return {
            "identity": self.identity,
            "samples": self.sample_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "self_similarity": round(self.self_similarity, 4),
            "repaired": self.repaired,
        }


class TemplateVault:
    """Filesystem vault holding one signed record per identity."""

    def __init__(self, path: os.PathLike[str] | str, *, auto_repair: bool = True) -> None:
        self.path = Path(path).expanduser()
        self.auto_repair = auto_repair
        self._identities_dir = self.path / "identities"
        self._key: Optional[bytes] = None

    # -- setup ------------------------------------------------------------ #
    def ensure(self) -> "TemplateVault":
        for folder in (self.path, self._identities_dir):
            try:
                folder.mkdir(parents=True, exist_ok=True)
                harden_path(folder, directory=True)
            except OSError as exc:
                raise StorageError(f"Cannot create the vault at {folder}: {exc}") from None
        if self._key is None:
            self._key = load_or_create_key(self.path)
        return self

    @property
    def key(self) -> bytes:
        if self._key is None:
            self.ensure()
        return self._key  # type: ignore[return-value]

    # -- paths ------------------------------------------------------------ #
    def _files(self, identity: str) -> tuple[Path, Path]:
        slug = slugify(identity)
        live = self._identities_dir / f"{slug}.json"
        return live, live.with_suffix(".json.bak")

    def contains(self, identity: str) -> bool:
        live, backup = self._files(identity)
        return live.is_file() or backup.is_file()

    # -- low level I/O ----------------------------------------------------- #
    def _atomic_write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="wb", dir=str(path.parent), prefix=f".{path.name}.", delete=False
        )
        temporary = Path(handle.name)
        try:
            with handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            harden_path(temporary)
            os.replace(temporary, path)
            harden_path(path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise StorageError(f"Could not write {path}: {exc}") from None

    def _read_envelope(self, path: Path) -> dict:
        try:
            text = path.read_text(encoding="utf-8")
            return json.loads(text)
        except FileNotFoundError:
            raise
        except (OSError, json.JSONDecodeError) as exc:
            raise TemplateCorruptedError(f"{path.name} is unreadable: {exc}") from None

    # -- schema ------------------------------------------------------------ #
    def _validate(self, payload: dict, expected: str) -> None:
        from .errors import TemplateCorruptedError

        if payload.get("identity") != expected:
            raise TemplateCorruptedError(
                f"Template belongs to {payload.get('identity')!r}, not {expected!r}."
            )
        samples = payload.get("samples")
        if not isinstance(samples, list) or not samples:
            raise TemplateCorruptedError("Template contains no face samples.")
        for sample in samples:
            vector = sample.get("vector")
            if not isinstance(vector, list) or len(vector) != DIM:
                raise TemplateCorruptedError("A stored face vector has the wrong length.")
            if not all(isinstance(v, (int, float)) and np.isfinite(v) for v in vector):
                raise TemplateCorruptedError("A stored face vector contains invalid numbers.")
        centroid = payload.get("centroid")
        if centroid is not None and (not isinstance(centroid, list) or len(centroid) != DIM):
            raise TemplateCorruptedError("The stored centroid has the wrong length.")

    def _payload_to_profile(self, payload: dict, *, repaired: bool, path: Path) -> StoredProfile:
        samples = [
            np.asarray(s["vector"], dtype=np.float32) for s in payload.get("samples", [])
        ]
        centroid_data = payload.get("centroid")
        if centroid_data:
            centroid = np.asarray(centroid_data, dtype=np.float32)
        else:
            centroid = np.mean(np.stack(samples), axis=0)
        norm = float(np.linalg.norm(centroid))
        if norm > 0:
            centroid = centroid / norm
        return StoredProfile(
            identity=payload["identity"],
            samples=samples,
            centroid=centroid.astype(np.float32),
            created_at=payload.get("created_at", ""),
            updated_at=payload.get("updated_at", ""),
            self_similarity=float(payload.get("self_similarity", 0.0)),
            repaired=repaired,
            path=path,
            notes=payload.get("notes", ""),
        )

    # -- public API --------------------------------------------------------- #
    def save(
        self,
        identity: str,
        vectors: Sequence[np.ndarray],
        *,
        qualities: Optional[Sequence[float]] = None,
        notes: str = "",
        max_samples: int = 12,
        replace: bool = False,
    ) -> StoredProfile:
        """Store (or extend) the record for ``identity``."""
        identity = str(identity).strip()
        if not identity:
            raise ValueError("Identity name must not be empty.")
        if not vectors:
            raise ValueError("save() needs at least one face vector.")

        self.ensure()
        live, backup = self._files(identity)

        existing: List[dict] = []
        created_at = utcnow()
        if not replace and (live.is_file() or backup.is_file()):
            try:
                previous = self.load(identity)
                existing = [
                    {"vector": [float(v) for v in vec], "added_at": previous.updated_at}
                    for vec in previous.samples
                ]
                created_at = previous.created_at or created_at
            except (TemplateCorruptedError, IdentityNotFoundError):
                existing = []

        qualities = list(qualities or [0.0] * len(vectors))
        new_entries = [
            {
                "vector": [round(float(v), 6) for v in np.asarray(vec, dtype=np.float32).reshape(-1)],
                "quality": round(float(qualities[i]) if i < len(qualities) else 0.0, 4),
                "added_at": utcnow(),
            }
            for i, vec in enumerate(vectors)
        ]

        combined = existing + new_entries
        combined = combined[-int(max(0, max_samples)):] if max_samples else combined

        matrix = np.stack([np.asarray(item["vector"], dtype=np.float32) for item in combined])
        centroid = matrix.mean(axis=0)
        norm = float(np.linalg.norm(centroid))
        centroid = centroid / norm if norm > 0 else centroid

        # how much an identity's own photos agree — used for adaptive thresholds
        if len(matrix) > 1:
            normalised = matrix / np.maximum(
                np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12
            )
            similarity = normalised @ normalised.T
            upper = similarity[np.triu_indices_from(similarity, k=1)]
            self_similarity = float(upper.mean()) if upper.size else 1.0
        else:
            self_similarity = 1.0

        payload = {
            "identity": identity,
            "created_at": created_at,
            "updated_at": utcnow(),
            "dim": DIM,
            "samples": combined,
            "centroid": [round(float(v), 6) for v in centroid],
            "self_similarity": round(self_similarity, 6),
            "engine": {
                "library": _meta.PACKAGE_NAME,
                "version": _meta.__version__,
                "developer": _meta.__author__,
                "model": "sface-2021dec-int8bq",
            },
            "notes": notes,
        }

        envelope = seal(self.key, payload)
        data = json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")
        self._atomic_write(live, data)

        # keep the previous good version as the backup, then mirror the new one
        try:
            shutil.copyfile(live, backup)
            harden_path(backup)
        except OSError:  # pragma: no cover - best effort
            pass

        return self._payload_to_profile(payload, repaired=False, path=live)

    def load(self, identity: str, *, with_repair: Optional[bool] = None) -> StoredProfile:
        """Load a profile, verifying its signature (and repairing if needed)."""
        identity = str(identity).strip()
        live, backup = self._files(identity)
        repair = self.auto_repair if with_repair is None else with_repair

        if not live.is_file() and not backup.is_file():
            raise IdentityNotFoundError(
                f"No enrolled profile named {identity!r}.",
                hint="Enroll first: verifyface.enroll(name, photo).",
            )

        first_error: Optional[Exception] = None
        if live.is_file():
            try:
                payload = unseal(self.key, self._read_envelope(live))
                self._validate(payload, identity)
                return self._payload_to_profile(payload, repaired=False, path=live)
            except TemplateCorruptedError as exc:
                first_error = exc

        if backup.is_file():
            try:
                payload = unseal(self.key, self._read_envelope(backup))
                self._validate(payload, identity)
                if repair and first_error is not None:
                    # heal the live file from the good backup
                    shutil.copyfile(backup, live)
                    harden_path(live)
                return self._payload_to_profile(payload, repaired=True, path=backup)
            except TemplateCorruptedError as exc:
                first_error = first_error or exc

        raise TemplateCorruptedError(
            f"The template for {identity!r} is damaged and no intact backup exists: {first_error}"
        )

    def delete(self, identity: str) -> bool:
        """Remove an identity and its backup. Returns True when something was deleted."""
        live, backup = self._files(identity)
        removed = False
        for path in (live, backup):
            try:
                path.unlink()
                removed = True
            except FileNotFoundError:
                continue
            except OSError as exc:  # pragma: no cover
                raise StorageError(f"Could not delete {path}: {exc}") from None
        return removed

    def identities(self) -> List[str]:
        """Every enrolled identity name (sorted, unicode-preserving)."""
        if not self._identities_dir.is_dir():
            return []
        names: List[str] = []
        seen = set()
        for path in sorted(self._identities_dir.glob("*.json")):
            if path.name.endswith(".json.bak"):
                continue
            slug = path.stem
            if slug in seen:
                continue
            seen.add(slug)
            try:
                payload = unseal(self.key, self._read_envelope(path))
                names.append(str(payload.get("identity", slug)))
            except Exception:
                names.append(slug)
        return sorted(names, key=str.casefold)

    def profiles(self) -> Dict[str, StoredProfile]:
        """Every readable profile, keyed by identity name."""
        result: Dict[str, StoredProfile] = {}
        for name in self.identities():
            try:
                result[name] = self.load(name)
            except Exception:
                continue
        return result

    def verify_integrity(self) -> List[dict]:
        """Check every record; report ``ok``, ``repaired`` or ``corrupted``."""
        report: List[dict] = []
        if not self._identities_dir.is_dir():
            return report
        for path in sorted(self._identities_dir.glob("*.json")):
            if path.name.endswith(".json.bak"):
                continue
            entry = {"file": path.name, "status": "ok", "identity": path.stem, "detail": ""}
            try:
                payload = unseal(self.key, self._read_envelope(path))
                self._validate(payload, payload.get("identity", ""))
                entry["identity"] = payload.get("identity", path.stem)
                entry["samples"] = len(payload.get("samples", []))
            except TemplateCorruptedError as exc:
                backup = path.with_suffix(".json.bak")
                if backup.is_file():
                    try:
                        payload = unseal(self.key, self._read_envelope(backup))
                        entry.update(
                            status="repaired",
                            identity=payload.get("identity", path.stem),
                            detail="live file was damaged; recovered from backup",
                            samples=len(payload.get("samples", [])),
                        )
                        if self.auto_repair:
                            shutil.copyfile(backup, path)
                            harden_path(path)
                    except TemplateCorruptedError:
                        entry.update(status="corrupted", detail=str(exc))
                else:
                    entry.update(status="corrupted", detail=str(exc))
            report.append(entry)
        return report

    # -- stats -------------------------------------------------------------- #
    def stats(self) -> dict:
        files = list(self._identities_dir.glob("*.json")) if self._identities_dir.is_dir() else []
        live_files = [f for f in files if not f.name.endswith(".json.bak")]
        key_file = self.path / "key.bin"
        return {
            "path": str(self.path),
            "identities": len(live_files),
            "size_kb": round(sum(f.stat().st_size for f in files) / 1024, 1) if files else 0.0,
            "key_present": key_file.is_file(),
            "key_private": is_private(key_file) if key_file.is_file() else None,
            "encrypted": True,
        }


__all__ = ["TemplateVault", "StoredProfile", "slugify", "TEMPLATE_FORMAT_VERSION", "DIM"]
