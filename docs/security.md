# Security, privacy and the threat model

Developer: **Kaustav Kanti Ray**

This document says exactly what verifyface protects against, how, and — just as
importantly — what it does **not** protect against.

---

## What is stored

| Stored | Not stored |
|---|---|
| 128 float32 numbers per enrolled photo (≈ 512 bytes) | the photograph |
| a signature, an optional AES-256-GCM envelope | the file name of the original photo |
| timestamps, a quality score, self-consistency | EXIF, GPS, camera model |
| a random 256-bit key in `key.bin` (mode `0600`) | any network identifier |

A template is a *feature vector*, not a compressed face. It cannot be turned
back into a portrait; the SFace network is not invertible in practice.

---

## Layers of protection

### 1. Inputs are read-only

`load_image()` opens files with `read_bytes()`, decodes into a **new** buffer
and returns it. numpy arrays from the caller are copied (`np.array(..., copy=True)`)
before any processing. Nothing in the library ever opens an image path for
writing. A regression test hashes the file before and after `verify()` and also
checks that the modification time did not change.

This is what makes it impossible for verification to "corrupt" the face it is
reading.

### 2. Templates are signed

```
envelope = {
  "format": "verifyface-template", "version": 1,
  "algorithm": "aes-256-gcm" | "hmac-sha256",
  "nonce": "…", "payload": "…",
  "signature": "hex HMAC-SHA256 over (algorithm, nonce, payload)"
}
```

Sub-keys are derived from the master key with HMAC-SHA256 under distinct
labels (`verifyface/mac/v1`, `verifyface/enc/v1`), so signing and encryption
never share key material.

Reading a template verifies the signature **before** parsing the payload, using
`hmac.compare_digest` (constant time). A single flipped bit raises
`TemplateCorruptedError`.

### 3. Templates are encrypted (optional)

When `cryptography` is installed (`pip install "verifyface[secure]"`), the
payload is encrypted with AES-256-GCM using a fresh 12-byte nonce, with
`verifyface-template-v1` as associated data. Encrypt-then-MAC: the HMAC covers
the ciphertext, so tampering is caught even before decryption.

Without `cryptography`, templates stay signed but readable — the library says so
in `verifyface doctor`.

### 4. Writes are atomic and backed up

```
identities/<slug>.json       ← live template
identities/<slug>.json.bak   ← previous good template
```

Writing goes to a temporary file in the same directory, `fsync`, then
`os.replace` (atomic on POSIX and on Windows for same-volume files). A crash
cannot leave a truncated template. If the live file is damaged, `load()` falls
back to the backup, restores it, and sets `repaired=True` on the result.

### 5. Filesystem permissions

* vault directory `0700`
* `key.bin`, templates and backups `0600`
* verified by `verifyface doctor` and by the test suite

Unicode identity names are converted to a safe slug plus a 10-hex-character
hash of the exact name, so `"../../etc/passwd"` becomes
`_._etc_passwd _--bc7d2593d3` inside the vault and can never escape it.

### 6. Key handling

| Mode | How |
|---|---|
| Default | 32 random bytes from `secrets.token_bytes`, written with exclusive create so an existing key is never overwritten |
| Passphrase | `VERIFYFACE_KEY="my long passphrase"` → scrypt (n=2¹⁴, r=8, p=1) with a per-vault salt |
| Raw key | `VERIFYFACE_KEY=<64 hex chars>` |

Losing `key.bin` makes existing templates unreadable — that is the point. Keep
a backup of the vault folder if you care about the profiles.

---

## Liveness and presentation attacks

Two layers:

**Challenge–response.** Two random actions out of *turn left, turn right, nod,
move closer, blink*. YuNet's landmarks are tracked to confirm the geometry
really changed; a still image produces identical landmarks forever and never
completes a challenge. The turn challenges are mirror-safe: the first turn
accepts either direction and the second requires the opposite direction.

**Passive heuristics.** Laplacian energy (printed photos are soft), a periodic
peak in the FFT magnitude (screen moiré), large low-saturation bright regions
(glare), and colour richness. Scores below `passive_threshold` (default 0.35)
reject the frame.

### What this stops

* holding up a printed photo of the person,
* showing a still photo or a paused video on a phone,
* a photo held at a distance (fails the size/quality gates).

### What this does **not** stop

* a high-quality 3D mask or a silicone replica,
* a deepfake video call streamed into the camera,
* a person who is physically present but coerced.

No single-RGB-camera, open-source system can stop those. Treat verifyface as a
**convenient second factor**, and add a PIN, OTP or hardware token for anything
valuable.

---

## Threat model summary

| Attack | Protected? | Mechanism |
|---|---|---|
| Reading photos from disk | — | photos are never stored |
| Editing a template to impersonate someone | ✅ | HMAC-SHA256 (and GCM tag) |
| Corrupting a template to lock somebody out | ✅ | signature + automatic backup restore |
| Stealing the vault folder | ⚠️ partial | AES-256-GCM, but the key lives beside it unless `VERIFYFACE_KEY` is used |
| Replaying a stored photo into the camera | ✅ | challenge–response + passive checks |
| Printed photo / phone screen | ✅ | as above |
| 3D mask, deepfake, coercion | ❌ | out of scope |
| Network interception | ✅ | nothing is transmitted |
| Path traversal via names | ✅ | slugified names with hash suffix |
| Accidental modification of the input photo | ✅ | read-only decoding, copy-on-read |

---

## Hardening checklist for a real deployment

1. `pip install "verifyface[secure]"` so templates are encrypted.
2. Set `VERIFYFACE_KEY` from your secret manager, not a file on disk.
3. Put the vault on a full-disk-encrypted volume.
4. Use `threshold="strict"` for access control.
5. Require `liveness` for anything remote.
6. Log decisions (`result.as_dict()`) — but never log the images.
7. Add a second factor for high-value actions.
8. Run `verifyface doctor` in your CI or startup script.
9. Back up the vault folder (templates + key) together.

---

## Biometric-data notes

verifyface is designed to be GDPR/DPDP-friendly:

* data minimisation — a 512-byte template instead of a photograph,
* purpose limitation — you decide what to enroll,
* storage limitation — `vault.delete(name)` removes the template and its backup,
* integrity — signed, self-healing records,
* confidentiality — AES-256-GCM and `0600` permissions.

You remain the data controller; obtain consent before enrolling anyone.
