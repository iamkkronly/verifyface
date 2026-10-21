"""A face-verification API in ~15 lines with FastAPI.

    pip install "verifyface[fastapi]" uvicorn
    uvicorn examples.05_web_fastapi:app --reload

Then:
    curl -F name=kaustav -F files=@photo.jpg  http://127.0.0.1:8000/face/enroll
    curl -F name=kaustav -F file=@selfie.jpg  http://127.0.0.1:8000/face/verify

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import verifyface as vf
from verifyface.integrations.fastapi_ext import install

try:
    from fastapi import FastAPI
except ImportError:  # pragma: no cover
    raise SystemExit('FastAPI is not installed. Run: pip install "verifyface[fastapi]"')

app = FastAPI(
    title="verifyface demo API",
    description="Offline face verification. Developer: Kaustav Kanti Ray",
    version=vf.__version__,
)

# One line wires up /face/enroll, /face/verify, /face/identify, /face/people
verifier = install(app, prefix="/face", verifier=vf.Verifier(vault="demo-vault"))


@app.get("/")
def index() -> dict:
    return {
        "app": "verifyface demo",
        "developer": vf.__author__,
        "version": vf.__version__,
        "endpoints": ["/face/enroll", "/face/verify", "/face/identify", "/face/people"],
        "docs": "/docs",
    }
