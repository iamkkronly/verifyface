# Examples

Developer: Kaustav Kanti Ray

Every script here runs after a single `pip install verifyface`. Run them with
the fixtures in `../tests/fixtures` if you do not have your own photos.

| # | Script | What it shows | Extra install |
|---|---|---|---|
| 01 | `01_hello_verify.py` | enroll + verify in 20 lines | — |
| 02 | `02_enroll_from_folder.py` | batch enroll and identify a folder | — |
| 03 | `03_compare_two_photos.py` | stateless comparison, explained | — |
| 04 | `04_live_camera.py` | live scan with random challenges | `verifyface[camera]` |
| 05 | `05_web_fastapi.py` | REST API with `/face/*` routes | `verifyface[fastapi]` |
| 06 | `06_web_flask.py` | Flask + a small HTML page | `verifyface[flask]` |
| 07 | `07_streamlit_app.py` | full Streamlit page (camera + upload) | `streamlit` |
| 08 | `08_desktop_gui.py` | Tkinter desktop app | — (`python3-tk` on Linux) |
| 09 | `09_attendance_kiosk.py` | camera kiosk that logs to CSV | `verifyface[camera]` |

---

## 01 — Hello, verify

```bash
python examples/01_hello_verify.py ../tests/fixtures/person_a_1.jpg ../tests/fixtures/person_a_2.jpg
```

Same person, eleven years apart → `VERIFIED`.

## 02 — A folder of people

```bash
mkdir -p photos
cp ../tests/fixtures/person_a_1.jpg photos/kaustav-1.jpg
cp ../tests/fixtures/person_a_2.jpg photos/kaustav-2.jpg
cp ../tests/fixtures/person_b_1.jpg photos/riya.jpg
python examples/02_enroll_from_folder.py photos
```

## 03 — Compare two photos

```bash
python examples/03_compare_two_photos.py ../tests/fixtures/person_b_1.jpg ../tests/fixtures/person_b_2.jpg
```

## 04 — Live camera

```bash
python examples/04_live_camera.py enroll kaustav
python examples/04_live_camera.py verify kaustav
```

## 05 — FastAPI

```bash
uvicorn examples.05_web_fastapi:app --reload
curl -F name=kaustav -F files=@photo.jpg localhost:8000/face/enroll
curl -F name=kaustav -F file=@selfie.jpg localhost:8000/face/verify
```

## 06 — Flask

```bash
python examples/06_web_flask.py
# open http://127.0.0.1:5000
```

## 07 — Streamlit

```bash
streamlit run examples/07_streamlit_app.py
```

## 08 — Desktop app

```bash
python examples/08_desktop_gui.py
```

## 09 — Attendance kiosk

```bash
python examples/09_attendance_kiosk.py --enroll
python examples/09_attendance_kiosk.py
# look at the camera; attendance.csv fills up
```

---

### A note about `demo-vault`

Most examples store profiles in a local `demo-vault/` folder so you can delete
them without touching your real vault. That folder is in `.gitignore` — commit
it by accident and you publish somebody's biometric template, so please do not.
