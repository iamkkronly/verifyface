"""Django views — import them straight into any project.

    # urls.py
    from django.urls import path
    from verifyface.integrations.django_views import face_enroll, face_verify

    urlpatterns = [
        path("face/enroll/", face_enroll),
        path("face/verify/", face_verify),
    ]

Both views accept ``POST`` requests with ``multipart/form-data`` and return JSON.
They are CSRF-exempt so they work as a small API; remove ``@csrf_exempt`` when
calling them from a same-site form instead.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

from ..verify import Verifier

#: One shared verifier per process (the engine is thread safe).
verifier = Verifier()


def _django():
    """Import Django lazily so the module can be read without it installed."""
    from django.http import JsonResponse
    from django.views.decorators.csrf import csrf_exempt
    from django.views.decorators.http import require_POST

    return JsonResponse, csrf_exempt, require_POST


def _handle_enroll(request):
    JsonResponse, _, _ = _django()
    name = (request.POST.get("name") or "").strip()
    files = request.FILES.getlist("photos") or request.FILES.getlist("photo")
    if not name or not files:
        return JsonResponse({"ok": False, "error": "name and photos are required"}, status=400)
    try:
        result = verifier.enroll(name, [f.read() for f in files], overwrite=True)
        return JsonResponse({"ok": True, **result.as_dict()})
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc).split("\n")[0]}, status=400)


def _handle_verify(request):
    JsonResponse, _, _ = _django()
    name = (request.POST.get("name") or "").strip()
    photo = request.FILES.get("photo")
    if not name or photo is None:
        return JsonResponse({"ok": False, "error": "name and photo are required"}, status=400)
    try:
        result = verifier.verify(name, photo.read())
        return JsonResponse({"ok": True, **result.as_dict()})
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc).split("\n")[0]}, status=400)


def face_enroll(request):
    """Enroll a person from uploaded photos (``name`` + ``photos``)."""
    _, csrf_exempt, require_POST = _django()
    return csrf_exempt(require_POST(_handle_enroll))(request)


def face_verify(request):
    """Verify a photo against an enrolled person (``name`` + ``photo``)."""
    _, csrf_exempt, require_POST = _django()
    return csrf_exempt(require_POST(_handle_verify))(request)


__all__ = ["verifier", "face_enroll", "face_verify"]
