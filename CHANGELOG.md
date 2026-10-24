# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project follows [Semantic Versioning](https://semver.org).

Developer: Kaustav Kanti Ray

---

## [1.1.0] — 2026-10-24

Security release responding to an independent user test report. Everything below
is covered by new regression tests (`tests/test_guards.py`,
`tests/test_second_factor.py`, `tests/test_integrations.py`); the suite grew from
109 to 151 tests.

### Fixed

- **FastAPI adapter returned HTTP 500 on every upload.** Endpoint annotations
  were postponed strings, so Pydantic could not resolve `UploadFile`
  (`PydanticUserError`). The module now imports the FastAPI names at module
  level (still optional) and uses real annotations. The adapter also gained a
  `liveness` form field, `notes`, and returns `developer` in `/face/people`.
- **Ambiguity now resolves with a second factor** instead of being blocked by it
  (found while testing: a correct PIN was refused when a lookalike was enrolled).

### Added — twins, siblings and lookalikes

- `Verifier.lookalikes(threshold=0.5)` and `verifyface lookalikes` list enrolled
  pairs that the embedding cannot separate.
- **Ambiguity guard**, on by default in `standard`/`high_security`: `verify()`
  scores the probe against every enrolled identity and refuses when a second
  person lands within `ambiguity_margin` (0.06). `VerifyResult.ambiguous`,
  `.second_best` and `.reasons` explain the decision.
- **Second factor**: `set_pin` / `clear_pin` / `has_pin` / `check_pin`, plus the
  `pin=` argument on `verify()`. The PIN is stored as a salted scrypt hash
  inside the signed template (never in clear text), survives re-enrollment and
  is preserved when the face samples are replaced.
- New CLI commands `pin`, `clear-pin` and `lookalikes`; `verify --pin`,
  `--ask-pin`, `--liveness`, `--no-ambiguity-guard`; `list` shows a 🔒 marker;
  `doctor` reports lookalike pairs and how many identities have a second factor.

### Added — liveness and replay inside `verify()`

- `verify(..., liveness="auto" | "required" | "off")` runs the passive
  anti-spoofing check on the probe; `Verifier(require_liveness=True)` makes it
  the default; `profile="high_security"` turns it on.
- `VerifyResult.liveness_status` reports `not_checked` / `passed` / `failed`.
- **Replay detection**: the SHA-256 of each enrolled source image is stored
  (opt out with `Settings(store_source_hashes=False)`). A byte-identical probe
  sets `replayed_sample=True`; it warns under `standard` and refuses under
  `high_security` (`block_replay=True`, also available per call).

### Added — security profiles

`Verifier(profile="convenience" | "standard" | "high_security")` bundles the
threshold, liveness, ambiguity-guard and replay settings. `info()` reports the
whole posture.

### Changed

- **Robust identity centroid**: samples are now weighted by their agreement with
  the others, so one bad enrollment photo no longer drags the identity centre.
- The browser app gained PIN fields (enroll / verify / live), an anti-spoofing
  toggle, a lookalike warning banner and explicit "an upload cannot prove
  presence" guidance; new endpoints `GET /api/lookalikes` and `POST /api/pin`.
- `LiveSession` accepts `pin=`.
- Dev extras now include FastAPI, Flask and httpx so the adapters are tested in CI.

### Documented

- README and `docs/security.md` now state the twin failure with the reported
  numbers (0.54 / 0.79) instead of implying it is solved.
- FAQ: "Can it tell identical twins apart?" and "A photo of a photo passes".
- Bengali guide: new sections on twins and photo replay.

---

## [1.0.1] — 2026-10-21

### Fixed

- **Windows console crash** — the CLI now reconfigures stdout/stderr to UTF-8
  with `errors="replace"`, so `✔`/`✘` and unicode names (for example Bengali)
  no longer raise `UnicodeEncodeError` in a `cp1252`/`cp437` console or a
  redirected pipe.
- **Tkinter example** — `examples/08_desktop_gui.py` referenced `exc` outside
  its `except` block and could raise `NameError` while reporting an error.
- **`identify()`** — removed a dead adaptive-threshold calculation; ranking is
  by raw similarity and the adaptive relaxation only affects the final verdict,
  exactly as documented.

### Changed

- Lint gate pinned to `E,F,W,I,B,C4,RUF` in `pyproject.toml`; the codebase now
  passes it with zero findings.
- CLI tests decode child output explicitly as UTF-8.

---

## [1.0.0] — 2026-10-21

First public release.

### Added

- **Face verification** — `enroll`, `verify`, `identify`, `compare`,
  `same_face`-style helpers, all available as module functions and through the
  `Verifier` class.
- **Robust identity matching** — YuNet 5-point landmark alignment onto a
  canonical 112×112 template, SFace 128-d embeddings, centroid + best-sample
  blending, and an adaptive threshold that relaxes by at most 0.035.
- **Bundled models** — YuNet and SFace (int8 block-quantised, 11.7 MB total)
  inside the wheel; SHA-256 pinned; `verifyface download-models` for source
  checkouts.
- **Encrypted template vault** — HMAC-SHA256 signatures, optional AES-256-GCM,
  atomic writes, `*.bak` self-healing, owner-only permissions, unicode-safe
  identity slugs.
- **Read-only image handling** — paths, bytes, base64, data URIs, URLs, PIL
  images, file objects and numpy arrays; EXIF orientation; inputs are never
  modified.
- **Quality gates** — blur, exposure, face size, yaw and roll measured and
  reported.
- **Liveness** — random challenge–response (turn, nod, approach, blink),
  passive screen-replay heuristics, and the `LivenessTracker` state machine.
- **Live scan** — `scan_live()` for the desktop and the framework-agnostic
  `LiveSession` for servers and browsers.
- **Zero-dependency browser app** — `verifyface serve`, English/বাংলা, live
  scan + upload + enroll, JSON API.
- **CLI** — `enroll`, `verify`, `identify`, `compare`, `list`, `delete`,
  `doctor`, `download-models`, `serve`, `demo`, `info`, with `--json` output and
  meaningful exit codes.
- **Integrations** — FastAPI, Flask, Django, Streamlit, Gradio.
- **Documentation** — quickstart, API reference, CLI reference, security and
  threat model, architecture, integrations, FAQ, troubleshooting, and a full
  Bengali guide.
- **109 tests** covering the pipeline, adversarial input, tampering, repair,
  liveness geometry, the CLI and the HTTP API.

### Known limitations

- Single-camera passive liveness cannot stop 3-D masks or deepfakes.
- Identical twins remain the hardest case for any 128-d embedding.
- No built-in multi-tenant authentication for the demo web server.

[1.1.0]: https://github.com/iamkkronly/verifyface/releases/tag/v1.1.0
[1.0.1]: https://github.com/iamkkronly/verifyface/releases/tag/v1.0.1
[1.0.0]: https://github.com/iamkkronly/verifyface/releases/tag/v1.0.0
