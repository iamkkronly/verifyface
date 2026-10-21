# Troubleshooting

Developer: **Kaustav Kanti Ray**

Start with:

```bash
verifyface doctor
```

It checks the models, digests, vault, permissions, encryption, template
integrity and the camera, and prints a clear verdict.

---

## Installation

### `ImportError: libGL.so.1: cannot open shared object file`

You are on a slim Linux image. The default dependency is
`opencv-python-headless`, so this usually means an older OpenCV was already
installed. Fix it:

```bash
pip uninstall -y opencv-python opencv-contrib-python
pip install --force-reinstall opencv-python-headless verifyface
```

If you need an on-screen camera window, install the GUI build instead:

```bash
pip install "verifyface[camera]"
```

### `pip` tries to build OpenCV from source

You are on a platform without a wheel (rare: very old Python). Use Python
3.9–3.13, or install OpenCV first from conda:

```bash
conda install -c conda-forge opencv
pip install verifyface --no-deps
pip install numpy pillow
```

### `numpy` ABI errors after upgrading

```bash
pip install --upgrade --force-reinstall numpy opencv-python-headless verifyface
```

### Windows: `AttributeError: module 'cv2' has no attribute 'FaceDetectorYN'`

Your OpenCV is older than 4.5.4:

```bash
pip install --upgrade "opencv-python-headless>=4.8"
```

---

## Models

### `ModelNotFoundError`

The bundled models are missing (usually a partial install or a source checkout).

```bash
verifyface download-models
```

or point at a folder you already have:

```bash
export VERIFYFACE_MODEL_DIR=/opt/verifyface-models
```

### `Downloaded … failed its checksum check`

The downloaded file does not match the pinned SHA-256 — a proxy, a captive
portal or a corrupted cache. Delete the cache folder and retry:

```bash
rm -rf ~/.cache/verifyface/models
verifyface download-models --force
```

---

## Detection and quality

### `NoFaceFoundError` on a photo that clearly has a face

1. Check the face is at least 64 px wide (crop tighter or use a bigger image).
2. Check the photo is not rotated 90° — EXIF is honoured, but a manually
   rotated JPEG may not have EXIF.
3. Try `engine.embed(path, mode="center")` if there are many faces.
4. Lower the detection confidence: `vf.FaceEngine(detection_confidence=0.4)`.

### `LowQualityError: The face is too small`

Move the camera closer. The minimum is `min_face_size` (default 64 px); lower it
only if you accept weaker accuracy:

```python
settings = vf.Settings(min_face_size=48, min_sharpness=8)
verifier = vf.Verifier(settings=settings)
```

### Verification fails for the right person

* Look at `result.score`. If it is 0.30–0.40, the person is borderline.
* Enroll more photos in the conditions that fail (glasses, indoor light).
* Try `threshold="lenient"` to confirm the pipeline works, then decide.
* Check `result.quality.passed` — a blurry probe gives a weak embedding.

### Verification passes for the wrong person

That should not happen above 0.40, but if it does:

* Use `threshold="strict"`.
* Look at `result.score` — if it is above 0.5 for a stranger, you may have
  enrolled a photo of the wrong person, or two lookalikes.
* Re-enroll with clearer, single-person photos.

---

## Vault and templates

### `TemplateCorruptedError`

A template failed its signature check **and** its backup is unusable. Either the
file was edited, the disk is failing, or the key changed.

```bash
verifyface doctor          # shows which file
verifyface delete name
verifyface enroll name new_photo.jpg
```

If *every* template fails at once, the key file was replaced or `VERIFYFACE_KEY`
changed. Restore `key.bin` from a backup, or re-enroll everybody.

### `StorageError: Cannot create the vault`

Permissions. Choose a writable folder:

```bash
verifyface enroll name photo.jpg --vault ~/documents/faces
```

### Templates disappeared after moving to another machine

The key lives in `<vault>/key.bin`. Copy the whole vault folder, not only
`identities/`.

---

## Camera and live scan

### `CameraError: Could not open camera #0`

* Close Zoom/Teams/OBS, which may hold the device.
* Try another index: `vf.scan_live("name", camera=1)`.
* On Linux check `ls /dev/video*` and that your user is in the `video` group.
* In Docker you must pass the device explicitly:
  `docker run --device /dev/video0 …`

### The preview window does not open

`opencv-python-headless` has no GUI. Either install `verifyface[camera]`, or use
`verifyface serve` / `LiveSession`, which do not need a window on the server.

### The blink challenge never completes

Blink detection uses OpenCV's Haar eye cascade and needs a reasonably lit,
front-facing face with visible eyes. If your environment makes it unreliable,
limit the challenge pool to head movements:

```python
session = vf.LiveSession(
    identity="kaustav",
    challenge_pool=("turn_left", "turn_right", "nod", "come_closer"),
)
```

### A still photo passed a live scan

With `actions=0` the session only performs passive checks, which a good phone
screen can pass. Always run at least two challenges for real use:

```python
vf.LiveSession(identity="kaustav", actions=2)
```

---

## Web app

### Port already in use

```bash
verifyface serve --port 8010
```

### Camera does not start in the browser

Browsers require a secure context: `http://localhost` is fine, any other host
needs HTTPS. Plain `http://192.168.x.x:8000` will block `getUserMedia`.

### Embedding the page in an iframe shows a blank camera

Permission policy: add `allow="camera"` to the iframe. The server already sends
permissive frame headers.

---

## Performance

### It is slow on the first call

Models are loaded lazily. Warm up once at start-up:

```python
verifier.engine.warmup()
```

### Every request is slow behind a web server

Make sure you create **one** `Verifier` per process, not one per request. The
engine caches networks per thread.

---

## Still stuck?

Run these and include the output in an issue (never include photos or vault
files):

```bash
verifyface doctor --json
python -c "import verifyface, cv2, numpy, PIL; print(verifyface.__version__, cv2.__version__, numpy.__version__, PIL.__version__)"
```

<https://github.com/iamkkronly/verifyface/issues>
