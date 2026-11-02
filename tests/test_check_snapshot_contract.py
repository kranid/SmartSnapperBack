import base64
import json
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("POLZA_API_KEY", "test-api-key")

import main


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture()
def client():
    return TestClient(main.app)


def image_base64() -> str:
    return base64.b64encode(PNG_BYTES).decode("ascii")


def payload(**overrides):
    data = {
        "snapshotId": "snap-001",
        "snapnodes": [
            {
                "text": "Back",
                "actionable": True,
                "role": "button",
                "rect": {"left": 1, "top": 2, "right": 3, "bottom": 4},
            }
        ],
        "image_base64": image_base64(),
        "platform": "android",
        "capturedAt": "2026-06-10T17:09:39.968Z",
    }
    data.update(overrides)
    return data


def patch_llm(monkeypatch, content):
    calls = []

    def invoke(messages):
        calls.append(messages)
        return SimpleNamespace(content=content)

    monkeypatch.setattr(main, "check_snapshot_llm", SimpleNamespace(invoke=invoke))
    return calls


@pytest.mark.parametrize("path", ["/checkSnapshot", "/checksnapshot"])
def test_check_snapshot_accepts_both_routes_and_returns_issue(client, monkeypatch, path):
    calls = patch_llm(
        monkeypatch,
        json.dumps([
            {
                "message": "property role must be button",
                "recommendation": "Set role=button for this actionable element.",
                "rect": {"left": 1, "top": 2, "right": 3, "bottom": 4},
                "path": "root/button",
            }
        ]),
    )

    response = client.post(path, json=payload())

    assert response.status_code == 201
    body = response.json()
    assert body["taskId"].startswith("task-")
    assert body["snapshotId"] == "snap-001"
    assert body["status"] == "completed"
    assert body["violations"] == [{
        "message": "property role must be button",
        "recommendation": "Set role=button for this actionable element.",
        "rect": {"left": 1, "top": 2, "right": 3, "bottom": 4},
        "path": "root/button",
    }]
    image_url = calls[0][0].content[1]["image_url"]["url"]
    assert image_url.startswith("data:image/png;base64,")


def test_check_snapshot_accepts_issues_object_response(client, monkeypatch):
    patch_llm(monkeypatch, '{"issues": []}')

    response = client.post("/checkSnapshot", json=payload())

    assert response.status_code == 201
    assert response.json()["violations"] == []


def test_check_snapshot_rewrites_incorrect_data_url_mime(client, monkeypatch):
    calls = patch_llm(monkeypatch, "[]")
    wrong_data_url = f"data:image/jpeg;base64,{image_base64()}"

    response = client.post("/checkSnapshot", json=payload(image_base64=wrong_data_url))

    assert response.status_code == 201
    image_url = calls[0][0].content[1]["image_url"]["url"]
    assert image_url.startswith("data:image/png;base64,")


def test_check_snapshot_rejects_invalid_base64_before_llm_call(client, monkeypatch):
    calls = patch_llm(monkeypatch, "[]")

    response = client.post("/checkSnapshot", json=payload(image_base64="not base64"))

    assert response.status_code == 422
    assert "valid base64" in response.json()["message"][0]
    assert response.json()["statusCode"] == 422
    assert calls == []


def test_check_snapshot_rejects_unsupported_image_before_llm_call(client, monkeypatch):
    calls = patch_llm(
        monkeypatch,
        "[]",
    )
    text_base64 = base64.b64encode(b"plain text").decode("ascii")

    response = client.post("/checkSnapshot", json=payload(image_base64=text_base64))

    assert response.status_code == 422
    assert "Unsupported image format" in response.json()["message"][0]
    assert calls == []


def test_check_snapshot_returns_502_for_non_json_model_response(client, monkeypatch):
    patch_llm(monkeypatch, "not json")

    response = client.post("/checkSnapshot", json=payload())

    assert response.status_code == 502
    assert response.json() == {
        "message": ["Invalid JSON response from polza.ai."],
        "error": "Bad Gateway",
        "statusCode": 502,
    }


def test_check_snapshot_returns_502_for_missing_rect_coordinate(client, monkeypatch):
    patch_llm(
        monkeypatch,
        json.dumps([
            {
                "message": "missing coordinate",
                "recommendation": "Provide all four rectangle coordinates.",
                "rect": {"left": 1, "top": 2, "right": 3},
                "path": "",
            }
        ]),
    )

    response = client.post("/checkSnapshot", json=payload())

    assert response.status_code == 502
    assert response.json()["message"] == ["Invalid JSON response from polza.ai."]


def test_check_snapshot_returns_502_for_missing_recommendation(client, monkeypatch):
    patch_llm(
        monkeypatch,
        json.dumps([
            {
                "message": "property role must be button",
                "rect": {"left": 1, "top": 2, "right": 3, "bottom": 4},
                "path": "root/button",
            }
        ]),
    )

    response = client.post("/checkSnapshot", json=payload())

    assert response.status_code == 502
    assert response.json()["message"] == ["Invalid JSON response from polza.ai."]


@pytest.mark.parametrize("missing", ["snapshotId", "platform", "capturedAt", "snapnodes", "image_base64"])
def test_check_snapshot_requires_current_client_fields(client, monkeypatch, missing):
    calls = patch_llm(monkeypatch, "[]")
    request = payload()
    request.pop(missing)

    response = client.post("/checkSnapshot", json=request)

    assert response.status_code == 422
    assert response.json()["statusCode"] == 422
    assert response.json()["error"] == "Unprocessable Entity"
    assert any(missing in message for message in response.json()["message"])
    assert calls == []
