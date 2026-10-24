# API reference

Developer: Kaustav Kanti Ray · version 1.1.0

```python
import verifyface as vf
```

---

## Module level shortcuts

These use one process-wide `Verifier` with the default vault. They are the
right choice for scripts and small apps.

### `vf.enroll(identity, images, **kwargs) → EnrollmentResult`

```python
vf.enroll("kaustav", "photo.jpg")
vf.enroll("kaustav", ["a.jpg", "b.jpg", "c.jpg"])
vf.enroll("kaustav", "photo.jpg", overwrite=True)
```

| Parameter | Type | Meaning |
|---|---|---|
| `identity` | `str` | Any name, including unicode (`"কৌস্তভ"`). |
| `images` | source or list | See [image sources](#image-sources). |
| `overwrite` | `bool` | Replace the stored samples instead of adding. |
| `add` | `bool` | Add to the existing profile (default `True`). |
| `notes` | `str` | Free text stored with the profile. |

Raises `NoFaceFoundError`, `IdentityExistsError`, `ImageError`.

### `vf.verify(identity, image, **kwargs) → VerifyResult`

```python
r = vf.verify("kaustav", "selfie.jpg")
bool(r)              # True when matched
r.score              # cosine similarity, -1 … 1
r.threshold          # the cut-off that was applied
r.confidence         # 0 … 1, always agrees with r.matched
r.explain()          # one human sentence
r.as_dict()          # JSON-ready
```

Optional parameters:

| Parameter | Meaning |
|---|---|
| `threshold="strict"` | override the policy for this call |
| `adaptive=False` | disable the small threshold relaxation |
| `liveness="auto" \| "required" \| "off"` | passive anti-spoofing on the probe |
| `pin="1234"` | second factor, when one is set for the identity |
| `ambiguity_guard=False` | allow a pass even if a lookalike is enrolled |
| `check_replay=False` | skip the exact-replay check |
| `block_replay=True` | refuse instead of warn on an exact replay |

### `vf.identify(image, **kwargs) → IdentifyResult`

Compares against every enrolled profile and returns the best match.

```python
res = vf.identify("group.jpg")
res.identity          # None when nobody matched
res.ranking           # [('kaustav', 0.71), ('riya', 0.12)]
```

### `vf.compare(a, b, **kwargs) → CompareResult`

Stateless comparison — nothing is written to the vault.

### `vf.same_person(a, b) → bool`

Shortcut for `bool(vf.compare(a, b))`.

### `vf.identities() → list[str]` · `vf.remove(name) → bool`

Manage the default vault.

### `vf.configure(vault=…, threshold=…, model_dir=…, allow_download=…)`

Recreate the process-wide verifier.

---

## `Verifier`

```python
v = vf.Verifier(
    vault="data/faces",       # or a pathlib.Path
    threshold="balanced",     # preset name or float
    model_dir=None,           # custom .onnx folder
    allow_download=True,      # fetch models if the bundled ones are missing
    profile="standard",       # convenience | standard | high_security
    require_liveness=None,    # force passive liveness on every verify()
    ambiguity_guard=None,     # refuse twins/lookalikes (default on)
    ambiguity_margin=None,    # default 0.06
    block_replay=None,        # refuse an exact replay of an enrolled photo
)
```

| Profile | Threshold | Liveness | Ambiguity guard | Replay |
|---|---|---|---|---|
| `convenience` | lenient | off | off | warn |
| `standard` | balanced | off | on | warn |
| `high_security` | strict | required | on | blocked |

| Method | Returns | Notes |
|---|---|---|
| `enroll(identity, images, …)` | `EnrollmentResult` | |
| `verify(identity, image, …)` | `VerifyResult` | |
| `identify(image, candidates=None)` | `IdentifyResult` | restrict the gallery |
| `compare(a, b)` | `CompareResult` | |
| `enrolled(name)` / `in v` | `bool` | |
| `identities()` | `list[str]` | |
| `profile(name)` | `StoredProfile` | vectors, timestamps, self-consistency |
| `remove(name)` | `bool` | |
| `lookalikes(threshold=0.5)` | `[(a, b, score)]` | twins/siblings detected in the gallery |
| `set_pin(name, pin)` | `None` | second factor (scrypt-hashed, stored in the template) |
| `clear_pin(name)` | `None` | remove the second factor |
| `has_pin(name)` | `bool` | |
| `check_pin(name, pin)` | `bool` | constant-time |
| `info()` | `dict` | configuration + model digests + security posture |

### `StoredProfile`

```python
p = v.profile("kaustav")
p.identity, p.sample_count, p.self_similarity
p.created_at, p.updated_at
p.repaired            # True if this read used the backup
```

---

## `FaceEngine` — the raw pipeline

```python
engine = vf.FaceEngine()

faces = engine.detect_faces("photo.jpg")        # [DetectedFace(box, landmarks, score)]
emb = engine.embed("photo.jpg")                 # Embedding(vector, quality, face)
emb.vector                                      # np.float32[128], unit length
emb.quality.passed, emb.quality.as_dict()

engine.similarity(emb_a.vector, emb_b.vector)   # cosine
engine.compare("a.jpg", "b.jpg")                # CompareResult
engine.centroid([emb1, emb2])                   # average identity vector
engine.best_match(emb, {"kaustav": vec})        # (name, score)
engine.info()                                   # versions + SHA-256 of models
```

`embed()` accepts `mode="largest" | "strict" | "center"`,
`check_quality=True`, `strict_quality=False`.

---

## Results

All four result classes share the same conveniences:

```python
r.matched        # bool (VerifyResult, IdentifyResult, CompareResult)
bool(r)          # same value, so `if vf.verify(...)` works
r.as_dict()      # JSON-serialisable dict (contains the developer credit)
r.explain()      # one sentence for a human
```

`VerifyResult` adds `identity`, `score`, `threshold`, `base_threshold`,
`confidence`, `threshold_name`, `quality`, `liveness`, `repaired_template`, plus
the 1.1.0 guard fields:

| Field | Meaning |
|---|---|
| `ambiguous` | another enrolled person scores almost as high (twins) |
| `second_best` | `(name, score)` of that runner-up |
| `liveness_status` | `not_checked` / `passed` / `failed` |
| `replayed_sample` | the probe is byte-identical to an enrolled photo |
| `requires_second_factor` / `second_factor_ok` | PIN state |
| `reasons` | every guard that refused, in plain words |

`EnrollmentResult` adds `samples`, `self_similarity`, `quality`, `created`,
`duplicates_skipped`, `skipped_images`.

---

## Image sources

Everywhere an image is accepted you may pass:

```python
"photo.jpg"                          # path (unicode-safe on Windows)
Path("photo.jpg")
b"…"                                 # raw bytes
"data:image/jpeg;base64,…"           # data URI (browsers)
"base64:…"                           # plain base64
"https://example.com/face.jpg"       # URL (25 MB limit, allow_url=False to block)
numpy_array                          # BGR uint8 (copied, never modified)
Image.open("photo.jpg")              # PIL image (copied)
open("photo.jpg", "rb")              # file object
```

EXIF orientation is applied, so phone photos are never sideways.

---

## Liveness

```python
from verifyface.liveness import (
    ACTIONS,            # {'turn_left': 'Turn your head …', …}
    LivenessTracker,    # per-frame geometry checker
    LivenessReport,
    passive_check,      # (score, reasons) for one image
    random_actions,
    check,
)

score, reasons = passive_check("selfie.jpg")
report = check("selfie.jpg")            # single-photo liveness (weaker)
```

---

## Camera

```python
from verifyface.camera import (
    open_camera, read_frame, capture_photo, has_gui,
    scan_live, LiveSession, LiveResult,
)

cap = open_camera(0)          # cv2.VideoCapture
frame = capture_photo(0)      # single still
result = scan_live("kaustav") # full desktop session
```

### `LiveSession` state machine

```python
session = vf.LiveSession(
    identity="kaustav",
    mode="verify",            # or "enroll" / "capture"
    actions=2,                # number of random challenges (0 disables)
    passive_threshold=0.35,
    frame_budget=120,
)
state = session.begin()
state = session.feed(frame)   # dict, see below
```

| Key | Meaning |
|---|---|
| `status` | `prompt` · `done` · `error` |
| `prompt` | text to show the user |
| `progress` | 0 … 1 |
| `actions_required` / `actions_completed` | challenge bookkeeping |
| `passed` | final verdict |
| `result` | `LiveResult.as_dict()` when `done` |

---

## Storage

```python
from verifyface.store import TemplateVault

vault = TemplateVault("data/faces")
vault.save("kaustav", [vector], qualities=[0.9])
profile = vault.load("kaustav")
vault.identities()
vault.verify_integrity()     # [{'file':…, 'status':'ok'|'repaired'|'corrupted'}]
vault.stats()
vault.delete("kaustav")
```

---

## Errors

Every error inherits `vf.VerifyFaceError`; messages are written for humans and
carry a `hint`.

| Error | Raised when |
|---|---|
| `NoFaceFoundError` | no face in the photo |
| `MultipleFacesError` | `mode="strict"` and more than one face |
| `LowQualityError` | face too small / too blurry / too dark |
| `ImageError`, `UnsupportedInputError` | unreadable input |
| `IdentityNotFoundError` | unknown profile |
| `IdentityExistsError` | re-enrolling with `add=False, overwrite=False` |
| `TemplateCorruptedError` | signature failure and no usable backup |
| `ModelNotFoundError` | models missing and downloads disabled |
| `CameraError` | no webcam / closed |
| `StorageError` | vault not writable |

```python
try:
    vf.verify("kaustav", "selfie.jpg")
except vf.NoFaceFoundError as exc:
    print(exc, exc.hint)
```

---

## Environment variables

| Variable | Effect |
|---|---|
| `VERIFYFACE_VAULT` | default vault folder |
| `VERIFYFACE_HOME` | base data folder |
| `VERIFYFACE_THRESHOLD` | `balanced` / `strict` / `lenient` / float |
| `VERIFYFACE_MODEL_DIR` | folder containing the `.onnx` files |
| `VERIFYFACE_KEY` | master key (64 hex chars) or passphrase |
| `VERIFYFACE_NO_DOWNLOAD` | `1` forbids downloading models |
| `VERIFYFACE_CACHE` | model cache folder |
