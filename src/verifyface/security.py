"""Keys, signatures and (optional) encryption for stored templates.

Design
------
* A 256-bit master key is created once with the operating system's CSPRNG.
* The key file is written with ``0600`` permissions (owner read/write only).
* Two independent sub-keys are derived with HMAC-SHA256:
  ``k_mac`` signs every template (integrity), ``k_enc`` encrypts it (privacy).
* Templates are signed *and* encrypted (encrypt-then-MAC), so silent bit-rot,
  accidental edits and tampering are all detected before a template is used.
* AES-256-GCM is used when the optional ``cryptography`` package is installed;
  otherwise templates stay signed but unencrypted, and the library says so.

Nothing here ever stores a photograph.  A template is 128 float numbers.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import stat
from pathlib import Path
from typing import Tuple

from .errors import StorageError

KEY_FILE = "key.bin"
KEY_ENV = "VERIFYFACE_KEY"
ALG_HMAC = "hmac-sha256"
ALG_AES = "aes-256-gcm"

SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1


# --------------------------------------------------------------------------- #
# Optional AES-GCM
# --------------------------------------------------------------------------- #
def _aes_available() -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401

        return True
    except Exception:  # pragma: no cover - optional dependency
        return False


def _aes_encrypt(key: bytes, plaintext: bytes, aad: bytes) -> Tuple[bytes, bytes]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(12)
    return AESGCM(key).encrypt(nonce, plaintext, aad), nonce


def _aes_decrypt(key: bytes, ciphertext: bytes, nonce: bytes, aad: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(key).decrypt(nonce, ciphertext, aad)


# --------------------------------------------------------------------------- #
# File permissions
# --------------------------------------------------------------------------- #
def harden_path(path: Path, *, directory: bool = False) -> None:
    """Best-effort owner-only permissions (no-op on platforms without POSIX modes)."""
    try:
        mode = 0o700 if directory else 0o600
        os.chmod(path, mode)
    except (OSError, NotImplementedError):  # pragma: no cover - Windows
        pass


def is_private(path: Path) -> bool:
    """True when only the owner can read the file."""
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    if os.name == "nt":  # pragma: no cover - Windows ACLs are not visible here
        return True
    return not (mode & (stat.S_IRGRP | stat.S_IROTH))


# --------------------------------------------------------------------------- #
# Key handling
# --------------------------------------------------------------------------- #
def _derive_from_passphrase(passphrase: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        passphrase.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
        maxmem=128 * 1024 * 1024,
    )


def _derive_subkeys(master: bytes) -> Tuple[bytes, bytes]:
    mac = hmac.new(master, b"verifyface/mac/v1", hashlib.sha256).digest()
    enc = hmac.new(master, b"verifyface/enc/v1", hashlib.sha256).digest()
    return mac, enc


def load_or_create_key(vault_dir: Path) -> bytes:
    """Return the 32-byte master key for ``vault_dir``, creating it if needed.

    ``VERIFYFACE_KEY`` may hold either a 64-character hex key or a passphrase.
    A passphrase is stretched with scrypt and a per-vault salt.
    """
    env_value = os.environ.get(KEY_ENV, "").strip()
    if env_value:
        if len(env_value) == 64:
            try:
                return bytes.fromhex(env_value)
            except ValueError:
                pass
        salt_file = Path(vault_dir) / "salt.bin"
        if salt_file.is_file():
            salt = salt_file.read_bytes()
        else:
            salt = secrets.token_bytes(16)
            try:
                Path(vault_dir).mkdir(parents=True, exist_ok=True)
                salt_file.write_bytes(salt)
                harden_path(salt_file)
            except OSError as exc:  # pragma: no cover
                raise StorageError(f"Cannot write the vault salt: {exc}") from None
        return _derive_from_passphrase(env_value, salt)

    key_path = Path(vault_dir) / KEY_FILE
    if key_path.is_file():
        data = key_path.read_bytes()
        if len(data) != 32:
            raise StorageError(
                f"The vault key at {key_path} is damaged ({len(data)} bytes instead of 32). "
                "Restore it from a backup, or delete the vault and enroll again."
            )
        return data

    try:
        Path(vault_dir).mkdir(parents=True, exist_ok=True)
        harden_path(Path(vault_dir), directory=True)
    except OSError as exc:
        raise StorageError(f"Cannot create the vault directory {vault_dir}: {exc}") from None

    key = secrets.token_bytes(32)
    temporary = key_path.with_suffix(".tmp")
    # exclusive create: never overwrite an existing key (that would orphan templates)
    try:
        with open(temporary, "xb") as handle:
            handle.write(key)
            handle.flush()
            os.fsync(handle.fileno())
        harden_path(temporary)
        os.replace(temporary, key_path)
        harden_path(key_path)
        if key_path.read_bytes() != key:  # pragma: no cover - paranoia
            raise StorageError("The vault key was not written correctly.")
    except FileExistsError:
        return key_path.read_bytes()
    except OSError as exc:  # pragma: no cover
        raise StorageError(f"Cannot create the vault key: {exc}") from None
    return key


# --------------------------------------------------------------------------- #
# Envelope signing / sealing
# --------------------------------------------------------------------------- #
def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def signature(k_mac: bytes, *, alg: str, nonce: str, payload: str) -> str:
    """Hex HMAC over the canonical envelope fields."""
    message = json.dumps(
        {"alg": alg, "nonce": nonce, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(k_mac, message, hashlib.sha256).hexdigest()


def seal(master: bytes, payload: dict, *, encrypt: bool = True) -> dict:
    """Turn ``payload`` into a signed (and, if possible, encrypted) envelope."""
    mac_key, enc_key = _derive_subkeys(master)
    plaintext = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")

    if encrypt and _aes_available():
        alg = ALG_AES
        ciphertext, nonce = _aes_encrypt(enc_key, plaintext, b"verifyface-template-v1")
        body, nonce_hex = _b64(ciphertext), _b64(nonce)
    else:
        alg = ALG_HMAC
        body, nonce_hex = _b64(plaintext), ""

    return {
        "format": "verifyface-template",
        "version": 1,
        "algorithm": alg,
        "nonce": nonce_hex,
        "payload": body,
        "signature": signature(mac_key, alg=alg, nonce=nonce_hex, payload=body),
    }


def unseal(master: bytes, envelope: dict) -> dict:
    """Verify and decrypt an envelope.

    Raises
    ------
    TemplateCorruptedError
        When the signature does not match or the ciphertext is damaged.
    """
    from .errors import TemplateCorruptedError

    if not isinstance(envelope, dict) or envelope.get("format") != "verifyface-template":
        raise TemplateCorruptedError("This is not a verifyface template.")

    alg = envelope.get("algorithm", "")
    nonce_hex = envelope.get("nonce", "") or ""
    body = envelope.get("payload", "") or ""
    expected = envelope.get("signature", "") or ""

    mac_key, enc_key = _derive_subkeys(master)
    actual = signature(mac_key, alg=alg, nonce=nonce_hex, payload=body)
    if not hmac.compare_digest(expected, actual):
        raise TemplateCorruptedError(
            "Template integrity check failed — the file was modified or damaged."
        )

    try:
        raw = _unb64(body)
        if alg == ALG_AES:
            plaintext = _aes_decrypt(enc_key, raw, _unb64(nonce_hex), b"verifyface-template-v1")
        elif alg == ALG_HMAC:
            plaintext = raw
        else:
            raise TemplateCorruptedError(f"Unknown template algorithm {alg!r}.")
        data = json.loads(plaintext.decode("utf-8"))
    except TemplateCorruptedError:
        raise
    except Exception as exc:
        raise TemplateCorruptedError(f"Template could not be opened: {exc}") from None

    if not isinstance(data, dict):
        raise TemplateCorruptedError("Template payload has an unexpected shape.")
    return data


def fingerprint(master: bytes) -> str:
    """Short, non-reversible key fingerprint for logs and `verifyface doctor`."""
    return hashlib.sha256(master).hexdigest()[:12]


def encryption_status() -> str:
    return ALG_AES if _aes_available() else "signed-only (install verifyface[secure] for AES-256-GCM)"


__all__ = [
    "KEY_FILE",
    "KEY_ENV",
    "ALG_AES",
    "ALG_HMAC",
    "load_or_create_key",
    "seal",
    "unseal",
    "signature",
    "fingerprint",
    "encryption_status",
    "harden_path",
    "is_private",
    "_aes_available",
]
