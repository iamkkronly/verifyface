# Contributing

Developer: **Kaustav Kanti Ray** · <https://github.com/iamkkronly/verifyface>

Thank you for wanting to improve verifyface. This project optimises for two
things at once: **a beginner must be able to use it in thirty seconds**, and
**a security reviewer must be able to trust it**. Please keep both in mind.

---

## Quick start

```bash
git clone https://github.com/iamkkronly/verifyface
cd verifyface
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
```

All tests must pass before you open a pull request.

---

## What we welcome

- Bug reports with a minimal reproduction (never include private photos).
- Better error messages — every error should tell the user what to do next.
- Documentation, examples, translations (Bengali, Hindi, Arabic, Spanish …).
- Platform reports: Windows, macOS, ARM, Raspberry Pi, Alpine, Docker.
- New framework adapters (Quart, Sanic, NiceGUI, Reflex …).
- Performance improvements that do not add heavy dependencies.

## What needs a discussion first

Open an issue before working on:

- changing the embedding model or the alignment template,
- changing default thresholds,
- new runtime dependencies,
- anything that changes the on-disk template format (needs a migration path),
- anything that touches the security model.

---

## Ground rules

1. **No new heavy dependencies.** `numpy`, `opencv-python-headless` and
   `pillow` are the only hard requirements, and that is deliberate.
2. **Never mutate user input.** Images are read-only, arrays are copied. A test
   enforces this.
3. **Never store photographs.** Templates only.
4. **Every new error gets a `hint`** telling the user what to do.
5. **Every public function gets a docstring and a type hint.**
6. **Credit stays.** Every source file keeps the `Developer: Kaustav Kanti Ray`
   line.
7. **Test with real failure modes** — dark photos, tilted heads, two faces,
   corrupt templates.

---

## Style

- Line length 100, `ruff` clean.
- `from __future__ import annotations` at the top of every module.
- Prefer clarity over cleverness; this library is read by beginners.
- Docstrings: what it does, parameters, raises, one example.

```bash
ruff check src tests
mypy src        # best effort; not a merge blocker
```

---

## Commit messages

```
feat: add Quart adapter
fix: keep EXIF rotation for PNG inputs
docs: explain the adaptive threshold in the FAQ
test: cover a corrupted backup file
perf: cache the aligned crop during quality checks
```

---

## Pull request checklist

- [ ] `pytest -q` passes (109 tests and growing)
- [ ] new behaviour is covered by a test
- [ ] docs updated (`README.md`, `docs/*.md`, `CHANGELOG.md`)
- [ ] no secrets, no personal photos, no vault files committed
- [ ] the credit line is intact in every file you touched

---

## Reporting security issues

Please **do not** open a public issue for a security problem — see
[SECURITY.md](SECURITY.md).

---

## License

By contributing you agree that your work is released under the MIT License and
that the project is credited to **Kaustav Kanti Ray**.
