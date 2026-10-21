"""Configuration: defaults, environment variables and paths.

Everything can be configured either with an argument, an environment variable
or an optional ``verifyface.toml`` / ``.verifyface.json`` file.  Arguments win,
then environment variables, then the config file, then the defaults.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .errors import ConfigError

# --------------------------------------------------------------------------- #
# Threshold presets
# --------------------------------------------------------------------------- #
# SFace cosine similarity, measured on the calibration set shipped in
# tests/fixtures (same person across 10+ years, different clothes/backgrounds
# scores 0.55-0.81; different people score -0.09 to 0.15).
THRESHOLD_PRESETS = {
    "strict": 0.480,     # very few false accepts, tolerant of false rejects
    "balanced": 0.400,   # default
    "lenient": 0.330,    # easiest to pass, use only for low-risk convenience
}

ENV_PREFIX = "VERIFYFACE_"


def _env(name: str) -> Optional[str]:
    value = os.environ.get(ENV_PREFIX + name)
    if value is None or value.strip() == "":
        return None
    return value.strip()


def default_home() -> Path:
    """Return the per-user data directory used for the vault."""
    override = _env("HOME")
    if override:
        return Path(override).expanduser()
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "verifyface"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "verifyface"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "verifyface"
    return Path.home() / ".verifyface"


def default_vault_path() -> Path:
    """Path of the template vault (encrypted biometric templates live here)."""
    override = _env("VAULT")
    if override:
        return Path(override).expanduser()
    return default_home() / "vault"


def resolve_threshold(value: object) -> float:
    """Turn ``"balanced"`` / ``0.42`` / ``None`` into a numeric threshold."""
    if value is None:
        preset = _env("THRESHOLD") or "balanced"
        return resolve_threshold(preset)
    if isinstance(value, bool):  # guard against True/False surprises
        raise ConfigError(f"Invalid threshold: {value!r}")
    if isinstance(value, (int, float)):
        number = float(value)
        if not 0.0 < number < 1.0:
            raise ConfigError(
                f"Threshold must be between 0 and 1 (got {number}). "
                "Typical values: 0.33 (lenient), 0.40 (balanced), 0.48 (strict)."
            )
        return number
    if isinstance(value, str):
        key = value.strip().lower()
        if key in THRESHOLD_PRESETS:
            return THRESHOLD_PRESETS[key]
        try:
            return resolve_threshold(float(key))
        except ValueError:
            raise ConfigError(
                f"Unknown threshold {value!r}. Choose one of "
                f"{', '.join(THRESHOLD_PRESETS)} or a number like 0.4."
            ) from None
    raise ConfigError(f"Invalid threshold: {value!r}")


@dataclass
class Settings:
    """Runtime settings for a :class:`~verifyface.Verifier`.

    All fields have sensible defaults; beginners never have to touch this class.
    """

    vault: Path = field(default_factory=default_vault_path)
    threshold: float = field(default_factory=lambda: resolve_threshold(None))
    detection_confidence: float = 0.6
    min_face_size: int = 64
    min_sharpness: float = 12.0
    min_brightness: float = 35.0
    max_brightness: float = 235.0
    max_yaw_degrees: float = 38.0
    max_roll_degrees: float = 30.0
    max_samples_per_identity: int = 12
    allow_download: bool = True
    auto_repair: bool = True
    model_dir: Optional[Path] = None

    def __post_init__(self) -> None:
        self.vault = Path(self.vault).expanduser()
        if self.model_dir is not None:
            self.model_dir = Path(self.model_dir).expanduser()
        if self.allow_download is True and (_env("NO_DOWNLOAD") or "").lower() in {"1", "true", "yes"}:
            self.allow_download = False

    # ------------------------------------------------------------------ #
    @classmethod
    def from_file(cls, path: os.PathLike[str] | str) -> "Settings":
        """Load settings from a JSON file (missing keys keep their defaults)."""
        file = Path(path).expanduser()
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ConfigError(f"Config file not found: {file}") from None
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Config file {file} is not valid JSON: {exc}") from None
        allowed = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        unknown = set(data) - allowed
        if unknown:
            raise ConfigError(f"Unknown config keys: {', '.join(sorted(unknown))}")
        return cls(**data)

    def as_dict(self) -> dict:
        data = {k: getattr(self, k) for k in self.__dataclass_fields__}  # type: ignore[attr-defined]
        data["vault"] = str(self.vault)
        if self.model_dir is not None:
            data["model_dir"] = str(self.model_dir)
        return data


def user_cache_dir() -> Path:
    """Directory used for downloaded models when the bundled ones are absent."""
    override = _env("CACHE")
    if override:
        return Path(override).expanduser()
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        return Path(base) / "verifyface" / "models"
    return Path.home() / ".cache" / "verifyface" / "models"


__all__ = [
    "THRESHOLD_PRESETS",
    "Settings",
    "default_home",
    "default_vault_path",
    "resolve_threshold",
    "user_cache_dir",
]
