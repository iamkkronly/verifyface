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
"""

from __future__ import annotations

from typing import List, Optional

from ..verify import Verifier


def create_router(verifier: Optional[Verifier] = None, *, prefix: str = "/face", tags=("face",)):
    """Build an :class:`fastapi.APIRouter` with the verification endpoints."""
    try:
        from fastapi import APIRouter, File, Form, HTTPException, UploadFile
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "FastAPI is not installed. Run: pip install \"verifyface[fastapi]\""
        ) from exc

    from ..errors import VerifyFaceError

    service = verifier or Verifier()
    router = APIRouter(prefix=prefix, tags=list(tags))

    def _read(upload: "UploadFile") -> bytes:
        data = upload.file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty file upload.")
        return data

    @router.get("/people")
    def people() -> dict:
        """List enrolled identities."""
        return {
            "ok": True,
            "identities": [service.profile(n).as_dict() for n in service.identities()],
        }

    @router.post("/enroll")
    def enroll(
        name: str = Form(...),
        files: List["UploadFile"] = File(...),
        overwrite: bool = Form(True),
    ) -> dict:
        """Enroll ``name`` from one or more uploaded photos."""
        try:
            result = service.enroll(name, [_read(f) for f in files], overwrite=overwrite)
            return {"ok": True, **result.as_dict(), "message": result.explain()}
        except VerifyFaceError as exc:
            raise HTTPException(status_code=400, detail=str(exc).split("\n")[0]) from None

    @router.post("/verify")
    def verify(name: str = Form(...), file: "UploadFile" = File(...)) -> dict:
        """Verify one photo against an enrolled person."""
        try:
            result = service.verify(name, _read(file))
            return {"ok": True, **result.as_dict(), "message": result.explain()}
        except VerifyFaceError as exc:
            raise HTTPException(status_code=400, detail=str(exc).split("\n")[0]) from None

    @router.post("/identify")
    def identify(file: "UploadFile" = File(...)) -> dict:
        """Find out who is in the photo."""
        try:
            result = service.identify(_read(file))
            return {"ok": True, **result.as_dict(), "message": result.explain()}
        except VerifyFaceError as exc:
            raise HTTPException(status_code=400, detail=str(exc).split("\n")[0]) from None

    @router.delete("/people/{name}")
    def delete(name: str) -> dict:
        return {"ok": True, "deleted": service.remove(name)}

    return router


def install(app, *, prefix: str = "/face", verifier: Optional[Verifier] = None) -> Verifier:
    """Attach the verification router to a FastAPI/Starlette application."""
    router = create_router(verifier, prefix=prefix)
    app.include_router(router)
    return verifier or Verifier()


__all__ = ["create_router", "install"]
