"""FastAPI adapter — three endpoints, one line of wiring.

    from fastapi import FastAPI
    from verifyface.integrations.fastapi_ext import install

    app = FastAPI()
    install(app, prefix="/face")

    # POST /face/enroll   (multipart: name + files[])
    # POST /face/verify   (multipart: name + file)
    # POST /face/identify (multipart: file)
    # GET  /face/people

Developer: Kaustav Kanti Ray

.. note::
   This module deliberately does **not** use ``from __future__ import
   annotations``.  FastAPI/Pydantic resolve endpoint annotations at runtime,
   and postponed (string) annotations cannot be resolved for names imported
   inside a function — that is exactly what produced HTTP 500 on every upload
   in 1.0.1.  The FastAPI names below are imported at module level, guarded so
   the dependency stays optional, and the annotations are real objects.
"""

import typing as _typing

try:  # optional dependency
    from fastapi import APIRouter, File, Form, HTTPException, UploadFile
    from fastapi import __version__ as _fastapi_version

    HAS_FASTAPI = True
except ImportError:  # pragma: no cover - exercised only without fastapi
    APIRouter = None  # type: ignore[assignment]
    File = None  # type: ignore[assignment]
    Form = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]
    UploadFile = None  # type: ignore[assignment]
    _fastapi_version = "not installed"
    HAS_FASTAPI = False

from .. import _meta
from ..verify import Verifier

__all__ = ["create_router", "install", "HAS_FASTAPI"]


def _require_fastapi() -> None:
    if not HAS_FASTAPI:
        raise ImportError(
            "FastAPI is not installed. Run: pip install \"verifyface[fastapi]\""
        ) from None


def create_router(verifier=None, *, prefix: str = "/face", tags=("face",)):
    """Build an :class:`fastapi.APIRouter` with the verification endpoints."""
    _require_fastapi()

    from ..errors import VerifyFaceError

    service = verifier or Verifier()
    router = APIRouter(prefix=prefix, tags=list(tags))

    def _read(upload):
        """Read an UploadFile without assuming a particular Starlette version."""
        stream = getattr(upload, "file", None)
        if stream is None:
            raise HTTPException(status_code=400, detail="Broken upload object.")
        try:
            stream.seek(0)
        except Exception:  # pragma: no cover - non-seekable streams
            pass
        data = stream.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty file upload.")
        return data

    def _fail(exc: Exception) -> "HTTPException":
        return HTTPException(status_code=400, detail=str(exc).split("\n")[0])

    @router.get("/people")
    def people():
        """List enrolled identities."""
        return {
            "ok": True,
            "identities": [service.profile(n).as_dict() for n in service.identities()],
            "developer": _meta.__author__,
        }

    @router.post("/enroll")
    def enroll(
        name: str = Form(...),
        files: _typing.List[UploadFile] = File(...),
        overwrite: bool = Form(True),
        notes: str = Form(""),
    ):
        """Enroll ``name`` from one or more uploaded photos."""
        try:
            result = service.enroll(
                name, [_read(f) for f in files], overwrite=overwrite, notes=notes
            )
            return {"ok": True, **result.as_dict(), "message": result.explain()}
        except VerifyFaceError as exc:
            raise _fail(exc) from None

    @router.post("/verify")
    def verify(
        name: str = Form(...),
        file: UploadFile = File(...),
        liveness: str = Form("off"),
    ):
        """Verify one photo against an enrolled person."""
        try:
            flag = str(liveness).strip().lower() in {"auto", "on", "true", "1", "required"}
            result = service.verify(name, _read(file), liveness="auto" if flag else "off")
            return {"ok": True, **result.as_dict(), "message": result.explain()}
        except VerifyFaceError as exc:
            raise _fail(exc) from None

    @router.post("/identify")
    def identify(file: UploadFile = File(...)):
        """Find out who is in the photo."""
        try:
            result = service.identify(_read(file))
            return {"ok": True, **result.as_dict(), "message": result.explain()}
        except VerifyFaceError as exc:
            raise _fail(exc) from None

    @router.delete("/people/{name}")
    def delete(name: str):
        return {"ok": True, "deleted": service.remove(name)}

    return router


def install(app, *, prefix: str = "/face", verifier=None) -> Verifier:
    """Attach the verification router to a FastAPI/Starlette application."""
    service = verifier or Verifier()
    app.include_router(create_router(service, prefix=prefix))
    return service
