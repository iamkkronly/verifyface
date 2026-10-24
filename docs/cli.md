# Command line reference

Developer: Kaustav Kanti Ray

```bash
verifyface [--version] <command> [options]
python -m verifyface <command>        # identical
```

Exit codes: `0` success / match, `1` no match, `2` error, `130` cancelled.

---

## `enroll`

```bash
verifyface enroll <name> <image> [<image> …] [--overwrite] [--json]
```

```bash
$ verifyface enroll kaustav photo1.jpg photo2.jpg
✔ enrolled 'kaustav' with 2 face sample(s) (self-consistency 0.71, quality 0.88).
```

* `--overwrite` replaces the previous samples instead of adding to them.
* Images without a usable face are reported and skipped; if *none* is usable the
  command fails with a clear message.

---

## `verify`

```bash
verifyface verify <name> <image> [--json]
```

```bash
$ verifyface verify kaustav selfie.jpg
✔ VERIFIED: 'kaustav' — similarity 0.612 (threshold 0.400, 97.6% confidence, very strong match)

$ verifyface verify kaustav selfie.jpg --liveness auto      # reject screens/prints
$ verifyface verify kaustav selfie.jpg --pin 1234           # second factor
$ verifyface verify kaustav selfie.jpg --ask-pin            # prompt (hidden input)

$ verifyface verify kaustav stranger.jpg ; echo $?
✘ NOT verified: 'kaustav' — similarity 0.131 (threshold 0.400, 1.8% confidence, different people)
1
```

---

## `identify`

```bash
verifyface identify <image> [--pin PIN | --ask-pin] [--json]
```

Compares against every enrolled person and prints the best match plus the two
runners-up.

---

## `compare`

```bash
verifyface compare <image_a> <image_b> [--json]
```

Stateless: nothing is stored, no name is needed.

---

## `pin` / `clear-pin`

```bash
verifyface pin kaustav            # prompts twice, input hidden
verifyface pin kaustav --pin 1234
verifyface clear-pin kaustav
```

A PIN turns the face into one of two factors — the only reliable way to
separate identical twins and very close siblings.

## `lookalikes`

```bash
$ verifyface lookalikes
! 1 lookalike pair(s) — twins/siblings score high here:
  • twin_a ↔ twin_b  0.790  (guarded)
  Advice: keep the ambiguity guard on and set a PIN for both people: verifyface pin <name>
```

## `list`

```bash
$ verifyface list
vault: /home/kaustav/.verifyface/vault
  • kaustav 🔒 PIN  2 sample(s), self-consistency 0.71, updated 2026-10-21T09:12:44+00:00
  • রিয়া    1 sample(s), self-consistency 1.00, updated 2026-10-20T18:03:10+00:00
```

---

## `delete`

```bash
verifyface delete <name> [--yes]
```

Removes the template and its backup. Asks for confirmation unless `--yes`.

---

## `doctor`

```bash
$ verifyface doctor
verifyface v1.1.1 — Developer: Kaustav Kanti Ray
python 3.13.1 • Linux-6.8-x86_64

  detector    ✔ model ready  face_detection_yunet_2023mar_int8bq.onnx 0.12 MB
  recognizer  ✔ model ready  face_recognition_sface_2021dec_int8bq.onnx 10.17 MB
  vault       /home/kaustav/.verifyface/vault
  encryption  aes-256-gcm
  camera      available (#0)
  templates   2 checked, 0 repaired, 0 corrupted

✔ everything looks good
```

Checks Python, numpy, OpenCV, Pillow, both model digests, the vault, the
encryption status, key fingerprint, every stored template and the camera.

---

## `download-models`

```bash
verifyface download-models [--dir FOLDER] [--force]
```

Only needed for source checkouts or if you want the models outside the wheel.
Digests are verified after download; a mismatch deletes the file and fails.

---

## `serve`

```bash
verifyface serve [--host 127.0.0.1] [--port 8000] [--vault PATH] [--open]
```

Starts the built-in browser app (live scan + upload + enroll, English/বাংলা).
Only the Python standard library is used on the server side.

To use it from another device on your network:

```bash
verifyface serve --host 0.0.0.0 --port 8000
```

> Only do this on a network you trust — the app exposes enrollment and
> verification endpoints without authentication.

---

## `demo`

```bash
verifyface demo [--camera 0] [--actions 2] [--save captured.jpg]
```

Opens the webcam, runs the liveness challenges, and optionally saves the
captured frame.

---

## `info`

```bash
verifyface info
```

JSON with the engine configuration, threshold, model paths and SHA-256 digests.

---

## Global options

| Option | Commands | Meaning |
|---|---|---|
| `--vault PATH` | all except `serve`/`download-models` | use another vault |
| `--threshold VALUE` | `enroll`, `verify`, `identify`, `compare` | `strict`, `balanced`, `lenient` or a number |
| `--pin PIN` / `--ask-pin` | `verify`, `identify` | second factor for a PIN-protected identity |
| `--json` | `enroll`, `verify`, `identify`, `compare`, `list`, `doctor` | machine-readable output |
