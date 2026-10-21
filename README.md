<div align="center">

# verifyface

**Enroll once. Verify anywhere. On any computer. Without the internet.**

Face verification for Python that a shopkeeper, a school teacher or a
first-time programmer can use — and that a security engineer can still trust.

![PyPI](https://img.shields.io/pypi/v/verifyface?label=pypi) ![Python](https://img.shields.io/badge/python-3.9%20%E2%80%93%203.13-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Offline](https://img.shields.io/badge/runs-100%25%20offline-success) ![Tests](https://img.shields.io/badge/tests-109%20passing-brightgreen)

**Developer: Kaustav Kanti Ray** · [GitHub](https://github.com/iamkkronly/verifyface) · [PyPI](https://pypi.org/project/verifyface/)

</div>

---

## The 30-second version

```bash
pip install verifyface
```

```python
import verifyface as vf

vf.enroll("kaustav", "my_photo.jpg")        # once
vf.verify("kaustav", "new_selfie.jpg")      # any time after that
# → VerifyResult(matched=True, score=0.61, confidence=0.97)
```

That is the whole library for most people. No account, no API key, no cloud,
no GPU, no model download — the face models ship inside the wheel.

---

## The promise: clothes, places and years do not matter

The hard part of face verification is not recognising a person in the *same*
photo. It is recognising them when everything around them has changed:

| Same person | Where / when | Measured similarity | Verdict |
|---|---|---|---|
| Macron 2014 vs Macron 2025 | 11 years apart, different suit, different building | **0.55** | ✅ same person |
| Ardern 2018 vs Ardern 2022 | different country, different clothes, different lighting | **0.68** | ✅ same person |
| Macron vs Ardern | two completely different people | **−0.08** | ❌ rejected |
| Macron vs Obama | two completely different people | **0.12** | ❌ rejected |

Those numbers come from the test suite in this repository, not from a slide
deck — the photos are public-domain and CC-licensed portraits, credited in
[`tests/fixtures/CREDITS.md`](tests/fixtures/CREDITS.md).

Why it works:

1. **Five landmarks → one canonical face.** YuNet finds the eyes, nose and mouth
   corners; the crop is rotated, scaled and sheared onto a fixed 112×112
   template, so pose and distance stop mattering.
2. **Identity, not appearance.** SFace turns the aligned face into 128 numbers
   that describe facial geometry and texture — not clothing, background or
   hairstyle.
3. **Several photos, one identity centre.** Enrolling two or three photos
   (different days, glasses on/off, bearded/clean-shaven) averages into a
   stable reference, and the threshold adapts to how much those photos differ.
4. **Quality gates.** Blurry, dark or badly turned photos are measured and
   handled explicitly instead of silently producing a wrong answer.

### "It must never corrupt the face"

This was a hard requirement, and it is enforced in four separate layers:

| Layer | What is guaranteed | Where |
|---|---|---|
| **Read-only inputs** | Every image is opened read-only and decoded into a *new* buffer. The caller's file, bytes or numpy array is never written to, never modified in place, never re-encoded. A test hashes the input file before and after verification. | `imageio.py` |
| **Signed templates** | Every stored template carries an HMAC-SHA256 signature (and AES-256-GCM encryption). A single flipped bit is detected before the template is used. | `security.py` |
| **Atomic writes** | Templates are written to a temp file, `fsync`ed and renamed over the old one — a power cut cannot leave a half-written record. | `store.py` |
| **Self-healing** | The last known-good copy is kept as `*.bak`. If the live template is damaged, it is restored automatically and the result is flagged `repaired_template=True`. | `store.py` |

So a damaged template can never impersonate somebody, and it can never lock
somebody out permanently either.

---

## Install

```bash
pip install verifyface                 # numpy + OpenCV + Pillow, models included
pip install "verifyface[secure]"       # + AES-256-GCM template encryption
pip install "verifyface[camera]"       # + on-screen live camera window
pip install "verifyface[fastapi]"      # + FastAPI adapter
pip install "verifyface[all]"          # everything
```

Works on **Windows, macOS, Linux, Raspberry Pi** and inside Docker on a
2-core CPU. Python 3.9 – 3.13. Total install ≈ 90 MB (OpenCV) of which 11 MB
is the face models.

---

## Quickstart

### 1. Enroll and verify

```python
import verifyface as vf

# One photo is enough to start.
vf.enroll("kaustav", "photo.jpg")

result = vf.verify("kaustav", "selfie.jpg")
if result:
    print(f"Welcome back — {result.confidence:.0%} confidence")
else:
    print(f"Not you ({result.score:.2f} < {result.threshold:.2f})")
```

### 2. Better: enroll from two or three photos

```python
vf.enroll("kaustav", ["front.jpg", "with_glasses.jpg", "from_2019.jpg"])
```

Photos from different days make verification more robust later. Near-duplicate
photos are detected and skipped automatically.

### 3. Compare two photos without storing anything

```python
r = vf.compare("before.jpg", "after.jpg")
print(r.matched, r.score, r.explain())
```

### 4. Who is this?

```python
who = vf.identify("group_photo.jpg")
print(who.identity, who.ranking)     # → 'kaustav', [('kaustav', 0.71), ...]
```

### 5. Profiles and thresholds

```python
v = vf.Verifier(vault="~/my-app/faces", threshold="strict")
v.enroll("kaustav", "photo.jpg")
v.verify("kaustav", "selfie.jpg")
v.identities()          # ['kaustav']
v.remove("kaustav")
```

| Threshold | Cut-off | Use it for |
|---|---|---|
| `lenient` | 0.33 | convenience logins, kiosks |
| `balanced` *(default)* | 0.40 | attendance, apps, most projects |
| `strict` | 0.48 | anything where a false accept is expensive |
| any float | e.g. `0.45` | your own calibration |

---

## Live scan (camera, with anti-spoofing)

A live scan asks for **two random actions** — turn your head, nod, move closer,
blink — and tracks the landmarks across frames to confirm each one happened.
A printed photo cannot nod. A phone playing a video cannot respond to a random
challenge.

```python
import verifyface as vf

result = vf.scan_live("kaustav")        # opens the webcam, draws the prompts
print(result.passed, result.liveness.explain())
```

Headless server, browser, phone, Raspberry Pi? Use the state machine instead —
it accepts frames from anywhere:

```python
session = vf.LiveSession(identity="kaustav")
state = session.begin()
while state["status"] != "done":
    state = session.feed(frame_bytes)    # JPEG/PNG bytes or a numpy frame
    print(state["prompt"])               # "Turn your head slowly to your left"
print(state["passed"], state["result"])
```

> **Honest limit:** the anti-spoofing here is challenge–response plus passive
> screen-replay heuristics. It stops casual photo/video attacks; it is not a
> certified PAD system and should not be the only factor for bank transfers.
> See [docs/security.md](docs/security.md).

---

## A complete browser app, zero extra dependencies

```bash
verifyface serve            # → http://localhost:8000
```

One page with three tabs — **live scan**, **photo upload**, **enroll** — in
English and বাংলা. It is written with the Python standard library only: no
Flask, no Node, no build step. Great for a school, an office reception or a
quick demo.

```
┌──────────────────────────────────────────────────────────────┐
│  📷 Live scan     🖼️ Photo verify     ➕ Enroll               │
├──────────────────────────────────────────────────────────────┤
│  Person: Kaustav ▾          ┌────────────────────────────┐    │
│  ┌───────────────────┐      │                            │    │
│  │ Start live scan   │      │      (camera preview)      │    │
│  └───────────────────┘      │                            │    │
│  Turn your head slowly…     └────────────────────────────┘    │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░  65%                                     │
└──────────────────────────────────────────────────────────────┘
```

---

## Command line (no programming at all)

```bash
verifyface enroll kaustav photo1.jpg photo2.jpg
verifyface verify  kaustav selfie.jpg          # exit code 0 = match, 1 = no match
verifyface identify group.jpg
verifyface compare before.jpg after.jpg
verifyface list
verifyface delete kaustav
verifyface doctor                              # checks models, vault, camera, integrity
verifyface serve --host 0.0.0.0 --port 8000
```

Everything supports `--json` for scripts, and `--vault` to keep profiles in a
project folder instead of your home directory.

---

## Add it to any platform

**FastAPI**
    ```python
    from fastapi import FastAPI
    from verifyface.integrations.fastapi_ext import install

    app = FastAPI()
    install(app, prefix="/face")
    # POST /face/enroll · POST /face/verify · POST /face/identify
    ```

**Flask**
    ```python
    from flask import Flask
    from verifyface.integrations.flask_ext import init_app

    app = Flask(__name__)
    init_app(app, url_prefix="/face")
    ```

**Streamlit**
    ```python
    from verifyface.integrations.streamlit_ui import render
    render()          # full page: camera, upload, enroll, verify
    ```

**Gradio**
    ```python
    from verifyface.integrations.gradio_ui import build
    build().launch()
    ```

**Django**
    ```python
    # urls.py
    from verifyface.integrations.django_views import face_enroll, face_verify

    urlpatterns = [
        path("face/enroll/", face_enroll),
        path("face/verify/", face_verify),
    ]
    ```

**Desktop (Tkinter)**
    ```bash
    python examples/08_desktop_gui.py
    ```

More in [examples/](examples) and [docs/integrations.md](docs/integrations.md).

---

## How it works

```
        any input                                     stored template
  path · URL · bytes · PIL · numpy                            │
            │                                                 │
            ▼                                                 ▼
   ┌─────────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
   │  load (read-    │──▶│ YuNet detect │──▶│ 5-point     │──▶│ SFace        │
   │  only, EXIF)    │   │ 5 landmarks  │   │ alignment    │   │ 128-d vector │
   └─────────────────┘   └──────────────┘   │ → 112×112    │   └──────┬───────┘
            │                               └──────────────┘          │
            │                                     │                   │
            ▼                                     ▼                   ▼
    quality report                     liveness / challenges     cosine similarity
    (blur, exposure, pose)             (live scans only)          vs threshold → result
```

* **YuNet** — 120 KB detector, 5 landmarks, ~10 ms per frame.
* **SFace** — 11 MB recogniser trained with the Sigmoid-constrained hypersphere
  loss; 99.40 % accuracy on LFW in the reference evaluation (int8 build used
  here: 99.32 %).
* Both run through **OpenCV's own DNN engine** — no PyTorch, no TensorFlow, no
  onnxruntime, and no Python-level deep-learning stack to break on install.

Full details: [docs/architecture.md](docs/architecture.md).

---

## Privacy

* **Photos are never stored.** Enrollment keeps 128 float32 numbers (≈ 1 KB) per
  sample. The original image is read and discarded.
* **Nothing leaves the machine.** No telemetry, no network calls at runtime.
  (`pip install` needs the internet; `verifyface doctor` is fully offline.)
* **Templates are encrypted** with AES-256-GCM and signed with HMAC-SHA256 when
  `cryptography` is installed; without it, they stay signed.
* **Owner-only permissions** — vault directory `0700`, files `0600`, master key
  in `key.bin` with `0600`.
* **Bring your own key** — set `VERIFYFACE_KEY` to a passphrase (stretched with
  scrypt) or a 64-hex-character key to keep the key out of the filesystem.

---

## Speed and footprint

| Operation | Time (2 vCPU container) |
|---|---|
| Load + detect + align + embed one photo | **≈ 60 ms** |
| Compare two photos (2 embeddings) | **≈ 82 ms** |
| Liveness frame check | **≈ 20 ms** |
| Wheel size | **11.7 MB** (models included) |
| RAM at runtime | **≈ 120 MB** |

---

## API at a glance

| Function | Purpose |
|---|---|
| `enroll(name, images, overwrite=False)` | register a person from 1–3 photos |
| `verify(name, image)` | is this the same person? → `VerifyResult` |
| `identify(image)` | who is this? → `IdentifyResult` |
| `compare(a, b)` | same person in both photos? → `CompareResult` |
| `same_person(a, b)` | `True` / `False` shortcut |
| `identities()` / `remove(name)` | manage profiles |
| `Verifier(vault=…, threshold=…)` | your own vault and policy |
| `scan_live(name)` / `LiveSession` | camera verification with challenges |
| `FaceEngine()` | raw detect / align / embed / similarity |
| `TemplateVault(path)` | the storage layer on its own |
| `verifyface.liveness` | passive + challenge-based liveness |

Every result object is truthy when it matched, converts to a dict with
`.as_dict()`, and explains itself in one sentence with `.explain()`.

Full reference: [docs/api.md](docs/api.md).

---

## Documentation

| Document | Contents |
|---|---|
| [docs/quickstart.md](docs/quickstart.md) | from zero to verified in 5 minutes |
| [docs/api.md](docs/api.md) | every class and function |
| [docs/cli.md](docs/cli.md) | command line reference |
| [docs/security.md](docs/security.md) | keys, templates, threat model, limits |
| [docs/architecture.md](docs/architecture.md) | how the pipeline works |
| [docs/integrations.md](docs/integrations.md) | FastAPI, Flask, Django, Streamlit, Gradio, Tkinter |
| [docs/faq.md](docs/faq.md) | common questions |
| [docs/troubleshooting.md](docs/troubleshooting.md) | when something goes wrong |
| [docs/বাংলা-গাইড.md](docs/বাংলা-গাইড.md) | বাংলায় সম্পূর্ণ গাইড |

---

## FAQ (short version)

**Do I need the internet after installing?** No. The models are in the wheel.

**Do I need a GPU?** No, a CPU is enough — ~60 ms per face.

**Does it work with clothes, beards, glasses, makeup?** Yes, those are not part
of the identity vector. Extreme changes (heavy sunglasses, face masks, a
decade of ageing plus a large weight change) reduce accuracy — enroll a couple
of photos in each condition you care about.

**Windows without a compiler?** No compilation is involved; every dependency
ships wheels.

**Is this a replacement for fingerprints?** No. It is a convenient second
factor, and honest about it. For high-value access combine it with a PIN, OTP
or a hardware token.

**What about identical twins?** Like every 128-d embedding system, twins are
the hardest case. Use the `strict` threshold and a second factor.

---

## Development

```bash
git clone https://github.com/iamkkronly/verifyface
cd verifyface
pip install -e ".[dev]"
pytest -q                 # 109 tests, ~25 s
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

---

## Credits

* **Design and development: [Kaustav Kanti Ray](https://github.com/iamkkronly)** — architecture, API,
  storage, liveness, CLI, web app, documentation.
* Face models: [OpenCV Zoo](https://github.com/opencv/opencv_zoo) — YuNet (Shiqi Yu et al.)
  and SFace (Yaoyao Zhong et al.), Apache-2.0.
* Test photographs: Wikimedia Commons contributors, public domain and CC
  licensed — see [tests/fixtures/CREDITS.md](tests/fixtures/CREDITS.md).

## License

MIT © 2026 **Kaustav Kanti Ray** — see [LICENSE](LICENSE).
