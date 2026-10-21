"""The built-in browser app's HTTP API.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import base64
import json
import threading
import urllib.error
import urllib.request

import pytest

from tests.conftest import fixture_path


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    from verifyface.web import create_server

    vault = tmp_path_factory.mktemp("web-vault")
    httpd, _state = create_server("127.0.0.1", 0, vault=str(vault))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


def post(base: str, path: str, payload: dict):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def data_uri(name: str) -> str:
    raw = fixture_path(name).read_bytes()
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()


def test_index_page_renders(server):
    with urllib.request.urlopen(server + "/", timeout=30) as response:
        html = response.read().decode()
    assert response.status == 200
    assert "verifyface" in html
    assert "Kaustav Kanti Ray" in html
    assert "Live scan" in html
    assert "বাংলা" in html


def test_health(server):
    with urllib.request.urlopen(server + "/api/health", timeout=30) as response:
        payload = json.loads(response.read())
    assert payload["ok"] is True
    assert payload["developer"] == "Kaustav Kanti Ray"


def test_enroll_verify_identify_flow(server):
    status, enrolled = post(server, "/api/enroll", {"name": "Kaustav", "images": [data_uri("person_a_1.jpg")]})
    assert status == 200 and enrolled["ok"] is True, enrolled
    assert enrolled["samples"] == 1

    status, verified = post(server, "/api/verify", {"name": "Kaustav", "image": data_uri("person_a_2.jpg")})
    assert status == 200 and verified["matched"] is True, verified

    status, impostor = post(server, "/api/verify", {"name": "Kaustav", "image": data_uri("impostor_2.jpg")})
    assert status == 200 and impostor["matched"] is False

    status, identified = post(server, "/api/identify", {"image": data_uri("person_a_2.jpg")})
    assert status == 200 and identified["identity"] == "Kaustav"

    with urllib.request.urlopen(server + "/api/list", timeout=30) as response:
        listing = json.loads(response.read())
    assert any(p["identity"] == "Kaustav" for p in listing["identities"])


def test_live_session_over_http(server):
    status, begin = post(server, "/api/live/begin", {"name": "Kaustav", "mode": "verify", "actions": 0})
    assert status == 200 and begin["ok"] is True
    session_id = begin["session_id"]

    status, state = post(server, "/api/live/frame", {"session_id": session_id, "image": data_uri("person_a_2.jpg")})
    assert status == 200
    assert state["status"] == "done"
    assert state["passed"] is True
    assert state["preview"].startswith("data:image/jpeg;base64,")

    # the session is consumed
    status, _again = post(server, "/api/live/frame", {"session_id": session_id, "image": data_uri("person_a_2.jpg")})
    assert status == 404


def test_live_session_requires_name(server):
    status, payload = post(server, "/api/live/begin", {"mode": "verify", "actions": 0})
    assert status == 400
    assert payload["ok"] is False


def test_errors_are_reported_as_json(server):
    status, payload = post(server, "/api/verify", {"name": "ghost", "image": data_uri("person_a_1.jpg")})
    assert status == 400
    assert "No enrolled profile" in payload["error"]

    status, payload = post(server, "/api/enroll", {"name": "", "images": []})
    assert status == 400

    status, payload = post(server, "/api/identify", {"image": "data:image/jpeg;base64,notanimage"})
    assert status == 400
