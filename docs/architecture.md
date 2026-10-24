# Architecture

Developer: Kaustav Kanti Ray

---

## Pipeline

```
input (path · URL · bytes · PIL · numpy · file object)
  │
  ├─ imageio.load_image ─────────────────────────────────────────────┐
  │     read-only · EXIF transpose · convert to BGR uint8 · copy      │
  │                                                                   │
  ├─ preprocess.FaceDetector (YuNet) ────────────────────────────────┤
  │     downscale to ≤1200 px for speed · NMS · 5 landmarks · sort    │
  │                                                                   │
  ├─ preprocess.select_face ──────────────────────────────────────────┤
  │     largest (default) · strict (reject >1) · center               │
  │                                                                   │
  ├─ preprocess.align_face ───────────────────────────────────────────┤
  │     least-squares similarity transform → 112×112 (LMEDS,           │
  │     Umeyama fallback)                                              │
  │                                                                   │
  ├─ preprocess.assess_quality ───────────────────────────────────────┤
  │     Laplacian variance · brightness · yaw/roll/pitch · face ratio  │
  │                                                                   │
  ├─ engine._forward (SFace) ─────────────────────────────────────────┤
  │     blob (raw BGR, scale 1.0) → 128-d → L2 normalise               │
  │                                                                   │
  └─ similarity ───────────────────────────────────────────────────────┘
        cosine · threshold preset · adaptive relax · confidence
```

Two ONNX files, both executed by `cv2.dnn`:

| Model | File | Size | Role |
|---|---|---|---|
| YuNet (int8 block-quantised) | `face_detection_yunet_2023mar_int8bq.onnx` | 120 KB | detection + landmarks |
| SFace / MobileFaceNet (int8 block-quantised) | `face_recognition_sface_2021dec_int8bq.onnx` | 10.2 MB | 128-d identity vector |

Bundling the models means `pip install verifyface` is the only step, ever. The
digests are checked against constants before first use; if a file is missing
(for example in a slim source checkout), `verifyface download-models` fetches
the same bytes from OpenCV Zoo.

---

## Why these decisions

**No PyTorch / TensorFlow / onnxruntime.** Each of them is a 100–800 MB
dependency that regularly fails to install on Windows, Alpine, ARM or Python
3.13. OpenCV already ships a CPU DNN engine and both models are plain ONNX.
Result: three dependencies, wheels on every platform, and a 60 ms forward pass.

**int8 block quantisation.** 3.5× smaller, ~10 % faster, and measured accuracy
on our calibration set differs by <0.001 (99.32 % vs 99.40 % on LFW for the
reference model). The right trade for a library meant to be installed anywhere.

**Alignment matters more than the network.** The single biggest reason a photo
from 2014 matches a photo from 2025 is that both are rotated/scaled/sheared
onto the same canonical 5-point template before embedding. Alignment uses
`estimateAffinePartial2D` with LMEDS and falls back to a hand-written Umeyama
similarity estimate, so it never fails on a weird landmark configuration.

**Centroid + best-sample blending.** A pure centroid is stable but can be pulled
by an outlier enrollment photo; a pure max over samples inflates false accepts.
`0.7 × centroid + 0.3 × best sample` behaves well in both directions.

**Adaptive threshold.** If a person's own enrollment photos already score 0.60
against each other (glasses on/off, ten years apart), demanding 0.48 from a new
photo is unfair. The threshold relaxes by at most 0.035, and never below 0.30 —
a bounded relaxation with a hard floor, not an open door.

---

## Storage format

```
~/.verifyface/
├── key.bin                       32 random bytes, 0600
├── salt.bin                      only when a passphrase is used
└── vault/
    ├── identities/
    │   ├── kaustav--c8687a08aa.json
    │   ├── kaustav--c8687a08aa.json.bak
    │   └── কৌস্তভ--6d70ee1074.json
    └── …
```

A template file:

```json
{
  "format": "verifyface-template",
  "version": 1,
  "algorithm": "aes-256-gcm",
  "nonce": "base64…",
  "payload": "base64 ciphertext of the JSON below",
  "signature": "hex HMAC-SHA256"
}
```

Decrypted payload:

```json
{
  "identity": "kaustav",
  "created_at": "2026-10-20T10:00:00+00:00",
  "updated_at": "2026-10-21T09:12:44+00:00",
  "dim": 128,
  "samples": [{"vector": [...128 floats...], "quality": 0.93, "added_at": "…"}],
  "centroid": [...128 floats...],
  "self_similarity": 0.71,
  "engine": {"library": "verifyface", "version": "1.0.1",
             "developer": "Kaustav Kanti Ray", "model": "sface-2021dec-int8bq"},
  "notes": ""
}
```

---

## Concurrency

* `FaceEngine` keeps **thread-local** OpenCV networks (`threading.local`), so a
  multi-threaded web server never shares a mutable DNN context.
* Enrollment/verification are pure functions over the vault; `TemplateVault`
  writes are atomic, so concurrent readers always see a complete file.
* `LiveSession` is per-user and must be kept per session (the web app stores it
  in a dictionary keyed by session id, with a 10-minute TTL).

Benchmarked with `ThreadingHTTPServer`: 6 concurrent verifications on 2 vCPU
complete in ~0.4 s wall clock with no corruption.

---

## Module map

| Module | Responsibility |
|---|---|
| `_meta.py` | version, author, credit banner |
| `config.py` | settings, env vars, threshold presets, paths |
| `errors.py` | one exception hierarchy with human hints |
| `imageio.py` | read-only decoding of every input type |
| `preprocess.py` | detection, selection, alignment, quality |
| `engine.py` | model resolution, embedding, comparison |
| `similarity.py` | thresholds, confidence, adaptive relaxation |
| `security.py` | keys, HMAC, AES-GCM, permissions |
| `store.py` | vault, atomic writes, backups, integrity |
| `verify.py` | `Verifier` + module-level API + result objects |
| `liveness.py` | challenges, passive anti-spoofing |
| `camera.py` | webcam, `LiveSession`, `scan_live` |
| `web.py` + `webapp/` | zero-dependency browser app |
| `cli.py` | `verifyface` command |
| `integrations/` | FastAPI, Flask, Django, Streamlit, Gradio |

---

## Test strategy

109 tests across eight files:

| File | Focus |
|---|---|
| `test_smoke.py` | metadata, credit, model digests, API surface |
| `test_imageio.py` | every input type, immutability of inputs |
| `test_verification.py` | same person years apart, impostors, thresholds, unicode |
| `test_security.py` | tampering, repair, permissions, path traversal, no photo bytes |
| `test_liveness.py` | geometry challenges, still-photo rejection, `LiveSession` |
| `test_similarity.py` | monotonic confidence, decision agreement |
| `test_cli.py` | subprocess end-to-end, exit codes, JSON |
| `test_web.py` | HTTP API, live session lifecycle |

Run them with `pytest -q` (~25 s on 2 vCPU, no network needed).
