"""Flask adapter.

    from flask import Flask
    from verifyface.integrations.flask_ext import init_app

    app = Flask(__name__)
    init_app(app, url_prefix="/face")

    #  POST /face/enroll    form: name, overwrite, files[]
    #  POST /face/verify    form: name, file
    #  POST /face/identify  form: file
    #  GET  /face/people

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

from typing import Optional

from ..verify import Verifier


def init_app(
    app,
    *,
    url_prefix: str = "/face",
    verifier: Optional[Verifier] = None,
) -> Verifier:
    """Register the verifyface blueprint on a Flask application."""
    try:
        from flask import Blueprint, jsonify, request
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "Flask is not installed. Run: pip install \"verifyface[flask]\""
        ) from exc

    from ..errors import VerifyFaceError

    service = verifier or Verifier()
    blueprint = Blueprint("verifyface", __name__)

    def _payload(files, name=None, overwrite=True):
        try:
            if name is not None:
                images = [f.read() for f in files]
                result = service.enroll(name, images, overwrite=overwrite)
            else:
                result = service.identify(files[0].read())
            return jsonify({"ok": True, **result.as_dict(), "message": result.explain()})
        except VerifyFaceError as exc:
            return jsonify({"ok": False, "error": str(exc).split("\n")[0]}), 400

    @blueprint.get("/people")
    def people():
        return jsonify(
            {"ok": True, "identities": [service.profile(n).as_dict() for n in service.identities()]}
        )

    @blueprint.post("/enroll")
    def enroll():
        files = request.files.getlist("files") or request.files.getlist("file")
        name = (request.form.get("name") or "").strip()
        if not name or not files:
            return jsonify({"ok": False, "error": "name and at least one file are required"}), 400
        overwrite = (request.form.get("overwrite") or "true").lower() in {"1", "true", "yes"}
        return _payload(files, name, overwrite)

    @blueprint.post("/verify")
    def verify():
        name = (request.form.get("name") or "").strip()
        file = request.files.get("file")
        if not name or file is None:
            return jsonify({"ok": False, "error": "name and file are required"}), 400
        try:
            result = service.verify(name, file.read())
            return jsonify({"ok": True, **result.as_dict(), "message": result.explain()})
        except VerifyFaceError as exc:
            return jsonify({"ok": False, "error": str(exc).split("\n")[0]}), 400

    @blueprint.post("/identify")
    def identify():
        file = request.files.get("file")
        if file is None:
            return jsonify({"ok": False, "error": "file is required"}), 400
        return _payload([file])

    @blueprint.delete("/people/<name>")
    def delete(name: str):
        return jsonify({"ok": True, "deleted": service.remove(name)})

    app.register_blueprint(blueprint, url_prefix=url_prefix)
    return service


__all__ = ["init_app"]
