# Quickstart — verified in five minutes

Developer: **Kaustav Kanti Ray** · [verifyface](../README.md)

---

## 1. Install

```bash
pip install verifyface
```

If you are on a system that only allows user installs:

```bash
pip install --user verifyface
```

Check that everything arrived:

```bash
verifyface doctor
```

You should see `everything looks good`, the two bundled models and a camera
status line.

---

## 2. Enroll your first face

Put one clear photo of yourself in a folder and run:

```bash
verifyface enroll kaustav my_photo.jpg
```

Or from Python:

```python
import verifyface as vf
print(vf.enroll("kaustav", "my_photo.jpg").explain())
```

What makes a good enrollment photo:

* the face is at least ~80 × 80 pixels in the picture,
* you look towards the camera (a slight angle is fine),
* normal indoor light — no strong backlight, no heavy shadow,
* **one** person in the frame.

Two or three photos taken on different days give noticeably better results:

```bash
verifyface enroll kaustav photo_2021.jpg photo_today.jpg photo_with_glasses.jpg
```

---

## 3. Verify

```bash
verifyface verify kaustav new_selfie.jpg
```

Exit code `0` means **same person**, `1` means **not the same person**, `2`
means **something went wrong** (missing file, no face, …). That makes it easy to
script:

```bash
if verifyface verify kaustav selfie.jpg; then
    echo "door opens"
else
    echo "access denied"
fi
```

From Python:

```python
import verifyface as vf

result = vf.verify("kaustav", "new_selfie.jpg")
print(result.matched, result.score, f"{result.confidence:.0%}")
```

---

## 4. Try the browser app

```bash
verifyface serve
```

Open <http://localhost:8000>. Three tabs:

1. **Live scan** — uses the webcam, asks two random challenges.
2. **Photo verify** — upload any photo.
3. **Enroll** — add a new person.

It is bilingual (English / বাংলা) and needs no extra packages.

---

## 5. Live camera from Python

```python
import verifyface as vf

result = vf.scan_live("kaustav")     # requires: pip install "verifyface[camera]"
print(result.passed, result.liveness.explain())
```

On a headless machine the same thing works through a frame-fed session — see
[integrations.md](integrations.md).

---

## 6. Put it in your own project

```python
# app.py
import verifyface as vf

# keep profiles next to the project, not in the home folder
verifier = vf.Verifier(vault="data/faces", threshold="strict")

def login(username: str, photo_path: str) -> bool:
    if not verifier.enrolled(username):
        return False
    return bool(verifier.verify(username, photo_path))
```

Add it to FastAPI, Flask, Django, Streamlit or Gradio in one line — see
[integrations.md](integrations.md).

---

## Where do the profiles live?

| Platform | Default vault |
|---|---|
| Linux | `~/.verifyface/vault` (or `$XDG_DATA_HOME/verifyface/vault`) |
| macOS | `~/Library/Application Support/verifyface/vault` |
| Windows | `%APPDATA%\verifyface\vault` |

Change it with `vf.Verifier(vault="…")`, `--vault …` on the CLI or
`VERIFYFACE_VAULT` in the environment.

Each person becomes one small JSON file (~2 KB) with a signature, an optional
encryption envelope, and a `.bak` copy of the last good version. No photos.

---

## Next

* [api.md](api.md) — every function, with parameters.
* [security.md](security.md) — what is stored, what is not, and the threat model.
* [faq.md](faq.md) — the questions everyone asks.
