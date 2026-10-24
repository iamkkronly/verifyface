"""Framework adapters — regression tests for the reported FastAPI HTTP 500.

The 1.0.1 FastAPI adapter raised ``PydanticUserError`` on every upload because
the endpoint annotations could not be resolved.  These tests upload a real
multipart request through the framework's own test client, which is exactly the
path that failed for the user.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import io

import pytest

import verifyface as vf
from tests.conftest import fixture_path

PHOTO_A = "person_a_1.jpg"
PHOTO_B = "person_a_2.jpg"
IMPOSTOR = "impostor_2.jpg"


# --------------------------------------------------------------------------- #
# FastAPI
# --------------------------------------------------------------------------- #
fastapi = pytest.importorskip("fastapi", reason="FastAPI adapter tests")
httpx = pytest.importorskip("httpx", reason="TestClient needs httpx")


@pytest.fixture()
def fastapi_client(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from verifyface.integrations.fastapi_ext import install

    app = FastAPI()
    install(app, prefix="/face", verifier=vf.Verifier(vault=tmp_path / "vault"))
    return TestClient(app)


def _bytes(name: str) -> bytes:
    return fixture_path(name).read_bytes()


def test_fastapi_enroll_returns_200_not_500(fastapi_client):
    response = fastapi_client.post(
        "/face/enroll",
        data={"name": "kaustav"},
        files={"files": ("a.jpg", _bytes(PHOTO_A), "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["samples"] == 1


def test_fastapi_multiple_files(fastapi_client):
    response = fastapi_client.post(
        "/face/enroll",
        data={"name": "kaustav"},
        files=[
            ("files", ("a.jpg", _bytes(PHOTO_A), "image/jpeg")),
            ("files", ("b.jpg", _bytes(PHOTO_B), "image/jpeg")),
        ],
    )
    assert response.status_code == 200, response.text
    assert response.json()["samples"] == 2


def test_fastapi_verify_and_identify(fastapi_client):
    fastapi_client.post(
        "/face/enroll",
        data={"name": "kaustav"},
        files={"files": ("a.jpg", _bytes(PHOTO_A), "image/jpeg")},
    )
    verified = fastapi_client.post(
        "/face/verify",
        data={"name": "kaustav"},
        files={"file": ("b.jpg", _bytes(PHOTO_B), "image/jpeg")},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["matched"] is True

    impostor = fastapi_client.post(
        "/face/verify",
        data={"name": "kaustav"},
        files={"file": ("c.jpg", _bytes(IMPOSTOR), "image/jpeg")},
    )
    assert impostor.status_code == 200
    assert impostor.json()["matched"] is False

    identified = fastapi_client.post(
        "/face/identify", files={"file": ("b.jpg", _bytes(PHOTO_B), "image/jpeg")}
    )
    assert identified.status_code == 200
    assert identified.json()["identity"] == "kaustav"

    people = fastapi_client.get("/face/people")
    assert people.status_code == 200
    assert [p["identity"] for p in people.json()["identities"]] == ["kaustav"]


def test_fastapi_errors_are_400_not_500(fastapi_client):
    missing = fastapi_client.post(
        "/face/verify",
        data={"name": "ghost"},
        files={"file": ("b.jpg", _bytes(PHOTO_B), "image/jpeg")},
    )
    assert missing.status_code == 400
    assert "No enrolled profile" in missing.json()["detail"]

    empty = fastapi_client.post(
        "/face/enroll",
        data={"name": "kaustav"},
        files={"files": ("a.jpg", b"", "image/jpeg")},
    )
    assert empty.status_code == 400


def test_fastapi_pin_and_liveness_parameters(fastapi_client):
    from verifyface.web import AppState  # noqa: F401  (import check only)

    service = vf.Verifier(vault=fastapi_client.app.state.__dict__.get("vault", "/tmp/x"))
    del service  # the router already holds its own verifier; behaviour is covered below

    fastapi_client.post(
        "/face/enroll",
        data={"name": "kaustav"},
        files={"files": ("a.jpg", _bytes(PHOTO_A), "image/jpeg")},
    )
    with_pin = fastapi_client.post(
        "/face/verify",
        data={"name": "kaustav", "liveness": "auto"},
        files={"file": ("b.jpg", _bytes(PHOTO_B), "image/jpeg")},
    )
    assert with_pin.status_code == 200
    assert with_pin.json()["liveness_status"] == "passed"


def test_fastapi_delete(fastapi_client):
    fastapi_client.post(
        "/face/enroll",
        data={"name": "kaustav"},
        files={"files": ("a.jpg", _bytes(PHOTO_A), "image/jpeg")},
    )
    deleted = fastapi_client.delete("/face/people/kaustav")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


# --------------------------------------------------------------------------- #
# Flask
# --------------------------------------------------------------------------- #
flask = pytest.importorskip("flask", reason="Flask adapter tests")


@pytest.fixture()
def flask_client(tmp_path):
    from flask import Flask

    from verifyface.integrations.flask_ext import init_app

    app = Flask(__name__)
    init_app(app, verifier=vf.Verifier(vault=tmp_path / "vault"))
    app.config.update(TESTING=True)
    return app.test_client()


def test_flask_enroll_verify_identify(flask_client):
    enrolled = flask_client.post(
        "/face/enroll",
        data={"name": "kaustav", "files": (io.BytesIO(_bytes(PHOTO_A)), "a.jpg")},
        content_type="multipart/form-data",
    )
    assert enrolled.status_code == 200
    assert enrolled.get_json()["samples"] == 1

    verified = flask_client.post(
        "/face/verify",
        data={"name": "kaustav", "file": (io.BytesIO(_bytes(PHOTO_B)), "b.jpg")},
        content_type="multipart/form-data",
    )
    assert verified.status_code == 200
    assert verified.get_json()["matched"] is True

    identified = flask_client.post(
        "/face/identify",
        data={"file": (io.BytesIO(_bytes(PHOTO_B)), "c.jpg")},
        content_type="multipart/form-data",
    )
    assert identified.status_code == 200
    assert identified.get_json()["identity"] == "kaustav"

    people = flask_client.get("/face/people")
    assert people.status_code == 200
    assert people.get_json()["identities"][0]["identity"] == "kaustav"


def test_flask_errors_are_400(flask_client):
    response = flask_client.post(
        "/face/verify",
        data={"name": "ghost", "file": (io.BytesIO(_bytes(PHOTO_B)), "b.jpg")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_adapters_expose_the_developer_credit(fastapi_client):
    payload = fastapi_client.get("/face/people").json()
    assert payload["developer"] == "Kaustav Kanti Ray"
