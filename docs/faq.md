# Frequently asked questions

Developer: Kaustav Kanti Ray

---

### Does it work without the internet?

Yes. The two ONNX models (11 MB) are inside the wheel. Nothing in `verify`,
`enroll`, `identify`, `compare`, `serve` or `doctor` touches the network.

### Do I need a GPU?

No. A 2-vCPU container embeds a face in about 60 ms. A Raspberry Pi 4 takes
about 180 ms per frame, which is fine for a door kiosk.

### Do I need to install PyTorch, TensorFlow or dlib?

No. OpenCV's own DNN engine runs both models. That is why `pip install` works
on Windows without a compiler, on Alpine, on ARM, and on Python 3.13.

### Why is it only 128 numbers per face?

SFace compresses an aligned face into a 128-dimensional embedding. That is
enough for 99 %+ verification accuracy while keeping templates tiny (≈ 512
bytes) and impossible to turn back into a photo.

### Will it recognise me in different clothes, a different city, next year?

Yes — that is the point of an identity embedding. The test suite verifies the
same person across 11 years, different suits, different buildings and different
cameras, with similarities between 0.55 and 0.81.

### Can it tell identical twins apart?

No — and no 128-dimensional face embedding can. Independent testing of 1.0.1
measured **0.54** and **0.79** for two twin pairs against a 0.40 threshold, i.e.
they were accepted. Since 1.1.0:

* `verifyface lookalikes` lists every enrolled pair that is too similar,
* the ambiguity guard **refuses** a verification when a second enrolled person
  scores within 0.06 of the claimed identity,
* `verifier.set_pin(name, "1234")` adds a second factor that *does* separate
  them — the face alone can no longer let either twin in.

So: **face only → still not enough for twins. Face + PIN → yes.** The PIN also
gates `identify()`: a 1:N search will not name a PIN-protected person without it.

### A photo of a photo passes. Is that a bug?

Comparing two identical *images* out of context always scores 1.0 — that is why
1.1.1 separates the two questions:

```python
vf.verify("kaustav", "photo.jpg", liveness="auto")      # passive screen/print filter
vf.verify("kaustav", "photo.jpg", liveness="required")  # proof of presence
```

`"auto"` is a filter: a clean upload still passes. `"required"` — and
`profile="high_security"` — needs evidence from a multi-frame live scan, so an
uploaded file, a pasted frame or a photo of a photo is **refused**
(`liveness_status="unproven"`). In 1.1.0 a still could wrongly be reported as
`"passed"`; that is fixed.

Uploading the exact enrolled file is also flagged (`replayed_sample=True`) and
blocked under `profile="high_security"`. For a real login use a live scan and,
for high-value actions, a second factor.

### What reduces accuracy?

| Situation | Effect |
|---|---|
| Heavy sunglasses / face mask | large — the eyes and lower face carry most identity |
| Extreme profile (> 40° turn) | large — rejected by the quality gate |
| Very low resolution (< 64 px face) | medium — rejected by the size gate |
| Strong backlight or darkness | medium — rejected by the quality gate |
| Ageing over decades + big weight change | medium — enroll photos from both periods |
| Twins / lookalikes | the hard case for every embedding model |

### Can I enroll several photos of the same person?

Yes, and you should: `vf.enroll(name, [a, b, c])`. Up to 12 samples are kept per
identity (`max_samples_per_identity`). Near-duplicates are skipped so a burst
of selfies does not skew the profile.

### What do the scores mean?

Cosine similarity between two 128-d vectors:

* **≥ 0.55** — very strong match
* **0.48 – 0.55** — strong match
* **0.40 – 0.48** — match at the default threshold
* **0.33 – 0.40** — weak
* **< 0.20** — different people

Different people in our calibration set scored −0.09 … 0.16, so the gap is wide.

### Can I change the threshold?

Yes: `vf.Verifier(threshold="strict")`, `verify(..., threshold=0.45)`, or
`VERIFYFACE_THRESHOLD=0.45`. Presets: `lenient` 0.33, `balanced` 0.40,
`strict` 0.48.

### Why did my verification pass at 0.36 when balanced is 0.40?

Because the profile's own photos agree less than usual (glasses on/off, years
apart), the adaptive threshold relaxed by at most 0.035 — with a hard floor of
0.30. You can disable it with `verify(..., adaptive=False)`.

### Where are the profiles stored?

`~/.verifyface/vault` on Linux, `~/Library/Application Support/verifyface/vault`
on macOS, `%APPDATA%\verifyface\vault` on Windows. Override with `vault=…` or
`VERIFYFACE_VAULT`.

### What happens if a template gets corrupted?

It is signed. On the next read the signature fails, verifyface restores the
`*.bak` copy automatically and reports `repaired=True`. If both copies are
destroyed the library raises `TemplateCorruptedError` instead of guessing. The
person can simply enroll again — their photo is not needed from the vault,
because it was never there.

### Does verifying modify my photo?

Never. Files are opened read-only and decoded into a fresh array; numpy inputs
are copied first. There is a test that hashes the input file before and after.

### Can two people use the same name?

No — one name, one profile. Use distinct names (or namespaces such as
`tenant/kaustav`, though `/` is sanitised into the slug and kept inside the
vault).

### Does it support unicode names?

Yes. `"কৌস্তভ কান্তি রায়"`, `"رِیا"`, `"张伟"` and even emoji names are stored
safely; the display name is preserved exactly and the file name is a sanitised
slug plus a hash.

### How do I delete a person?

`vf.remove("kaustav")` or `verifyface delete kaustav`. This removes the
template and its backup immediately.

### Can I use it commercially?

Yes — MIT license. Keep the copyright notice.

### Is it safe for banking or national ID?

No. Use it as one factor. See [security.md](security.md) for the threat model
and the honest limitations of single-camera liveness.

### Does it work with a webcam in a browser?

Yes: `verifyface serve`, or call `/api/live/frame` from your own front-end. The
camera is accessed by the browser, so it works even when the Python process
runs on a server (as long as the page is served over HTTPS or localhost).

### What if the face is not detected at all?

`NoFaceFoundError`. Common causes: face smaller than 64 px, heavy blur, profile
view beyond ~40°, or an extreme backlight. The error message tells the user what
to do.

### Does it send anything to a server?

No telemetry, no analytics, no update checks. The only network call in the
whole library is `download_models()` — and that is never used when the bundled
models are present.
