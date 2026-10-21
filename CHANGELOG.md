# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project follows [Semantic Versioning](https://semver.org).

Developer: **Kaustav Kanti Ray**

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

[1.0.1]: https://github.com/iamkkronly/verifyface/releases/tag/v1.0.1
[1.0.0]: https://github.com/iamkkronly/verifyface/releases/tag/v1.0.0
