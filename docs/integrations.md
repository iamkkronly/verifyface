# Integrations

Developer: Kaustav Kanti Ray

verifyface runs anywhere Python runs. These recipes cover the platforms people
ask about most.

---

## FastAPI

```python
from fastapi import FastAPI
from verifyface.integrations.fastapi_ext import install

app = FastAPI(title="Office entry")
verifier = install(app, prefix="/face", vault="data/faces")
```

| Method | Route | Body |
|---|---|---|
| `GET` | `/face/people` | — |
| `POST` | `/face/enroll` | multipart: `name`, `files[]`, `overwrite` |
| `POST` | `/face/verify` | multipart: `name`, `file` |
| `POST` | `/face/identify` | multipart: `file` |
| `DELETE` | `/face/people/{name}` | — |

```bash
curl -F name=kaustav -F file=@selfie.jpg http://localhost:8000/face/verify
# {"ok":true,"matched":true,"score":0.61,"confidence":0.97, …}
```

Run it with `uvicorn main:app --reload`.

---

## Flask

```python
from flask import Flask
from verifyface.integrations.flask_ext import init_app

app = Flask(__name__)
init_app(app, url_prefix="/face", vault="data/faces")
```

Routes mirror the FastAPI adapter. Templates for a small HTML form:

```html
<form action="/face/enroll" method="post" enctype="multipart/form-data">
  <input name="name" placeholder="Name">
  <input type="file" name="files" multiple accept="image/*">
  <button>Enroll</button>
</form>
```

---

## Django

```python
# urls.py
from django.urls import path
from verifyface.integrations.django_views import face_enroll, face_verify

urlpatterns = [
    path("face/enroll/", face_enroll),
    path("face/verify/", face_verify),
]
```

Both views are `POST` + multipart and return JSON. They are `csrf_exempt` so
they work as a small API; remove the decorator when using same-site forms.

---

## Streamlit

```python
import streamlit as st
from verifyface.integrations.streamlit_ui import render

st.set_page_config(page_title="Face check")
render()               # verify · enroll · people tabs, camera + upload
```

```bash
streamlit run app.py
```

---

## Gradio

```python
from verifyface.integrations.gradio_ui import build

build().launch()       # http://127.0.0.1:7860
```

Webcam and upload sources are both wired to `verify`, `enroll` and `identify`.

---

## Browser without a framework

```bash
verifyface serve --host 0.0.0.0 --port 8000
```

The page uses `getUserMedia` for the camera and posts JPEG frames to
`/api/live/frame`. Useful API endpoints if you want to build your own UI:

| Route | Payload |
|---|---|
| `POST /api/enroll` | `{"name": "...", "images": ["data:image/jpeg;base64,…"]}` |
| `POST /api/verify` | `{"name": "...", "image": "data:…"}` |
| `POST /api/identify` | `{"image": "data:…"}` |
| `POST /api/compare` | `{"a": "data:…", "b": "data:…"}` |
| `POST /api/live/begin` | `{"name": "...", "mode": "verify", "actions": 2}` |
| `POST /api/live/frame` | `{"session_id": "...", "image": "data:…"}` |
| `GET /api/list` | — |
| `POST /api/delete` | `{"name": "..."}` |

---

## Tkinter desktop app

`examples/08_desktop_gui.py` is a complete Windows/macOS/Linux window with
enroll, verify and webcam capture. It uses only the standard library plus
verifyface — no Electron, no browser.

```bash
python examples/08_desktop_gui.py
```

---

## Mobile / React Native / Flutter

Keep verification on the server: capture a frame on the phone, send it as a
base64 data URI to `/api/verify` (or your FastAPI endpoint) and show the
boolean. This is intentional — the template should never live on a device you
do not control.

```javascript
const res = await fetch("/api/verify", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({name: "kaustav", image: dataUrl}),
});
const {matched, confidence} = await res.json();
```

---

## Raspberry Pi / kiosk

```bash
sudo apt install -y python3-opencv libatlas-base-dev
pip install verifyface
verifyface enroll kaustav admin_photo.jpg
python -c "import verifyface as vf; print(vf.scan_live('kaustav').passed)"
```

Measured at ~180 ms per frame on a Pi 4 — smooth enough for a door kiosk.

---

## Docker

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir verifyface
WORKDIR /app
ENV VERIFYFACE_VAULT=/data/vault
VOLUME ["/data"]
CMD ["verifyface", "serve", "--host", "0.0.0.0", "--port", "8000"]
```

`opencv-python-headless` is the default dependency, so no X11 is required.
Mount `/data` to persist the vault (templates + key).

---

## Word/school office usage (no code)

```bash
verifyface serve            # reception laptop
verifyface enroll student1 photo.jpg
verifyface verify student1 today.jpg
```

For a folder of people:

```bash
for f in students/*.jpg; do
  name=$(basename "$f" .jpg)
  verifyface enroll "$name" "$f"
done
```
