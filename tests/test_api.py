"""后端 API 测试：使用内存替身，不依赖真实 Ganache/MySQL。"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from flask import Flask

from backend.app import create_app


def make_config(**overrides):
    values = {
        "max_content_length": 4 * 1024 * 1024,
        "max_file_mb": 2,
        "cors_origins": ("*",),
        "contract_address": "0x00000000000000000000000000000000000000A1",
        "debug": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture()
def app(service) -> Flask:
    return create_app(config=make_config(), service=service)


@pytest.fixture()
def client(app):
    return app.test_client()


def test_index_and_health(client):
    index = client.get("/api")
    assert index.status_code == 200
    assert index.get_json()["success"] is True

    health = client.get("/api/health")
    assert health.status_code == 200
    payload = health.get_json()
    assert payload["success"] is True
    assert payload["data"]["ok"] is True


def test_upload_and_verify_api(client):
    response = client.post(
        "/api/evidence",
        data={
            "file": (io.BytesIO(b"api integration content"), "note.txt"),
            "user_name": "API 测试员",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["status"] == "verified"
    assert data["file_hash"]
    assert data["block_number"] == 7
    assert data["user_name"] == "API 测试员"

    verify = client.post(
        "/api/verify",
        data={"file": (io.BytesIO(b"api integration content"), "note.txt")},
        content_type="multipart/form-data",
    )
    assert verify.status_code == 200
    assert verify.get_json()["data"]["status"] == "verified"

    by_hash = client.post(
        "/api/verify", json={"hash": data["file_hash"], "user_name": "查询员"}
    )
    assert by_hash.status_code == 200
    assert by_hash.get_json()["data"]["status"] == "verified"

    detail = client.get(f"/api/evidence/{data['file_hash']}")
    assert detail.status_code == 200
    assert detail.get_json()["data"]["file_hash"] == data["file_hash"]

    changed = client.post(
        "/api/verify",
        data={"file": (io.BytesIO(b"different"), "note.txt")},
        content_type="multipart/form-data",
    )
    assert changed.status_code == 200
    assert changed.get_json()["data"]["status"] == "not_found"


def test_upload_requires_file_and_user(client):
    no_file = client.post("/api/evidence", data={"user_name": "someone"})
    assert no_file.status_code == 400
    assert no_file.get_json()["error"]["code"] == "VALIDATION_ERROR"

    no_user = client.post(
        "/api/evidence",
        data={"file": (io.BytesIO(b"content"), "a.txt")},
        content_type="multipart/form-data",
    )
    assert no_user.status_code == 400
    assert "操作人" in no_user.get_json()["error"]["message"]


def test_duplicate_returns_409_with_detail(client):
    payload = {
        "file": (io.BytesIO(b"duplicate content"), "a.txt"),
        "user_name": "tester",
    }
    first = client.post("/api/evidence", data=payload, content_type="multipart/form-data")
    assert first.status_code == 201
    second = client.post(
        "/api/evidence",
        data={
            "file": (io.BytesIO(b"duplicate content"), "a.txt"),
            "user_name": "tester",
        },
        content_type="multipart/form-data",
    )
    assert second.status_code == 409
    error = second.get_json()["error"]
    assert error["code"] == "ALREADY_EXISTS"
    assert error["detail"]["file_hash"] == first.get_json()["data"]["file_hash"]


def test_verify_validation_and_not_found(client):
    no_input = client.post("/api/verify", json={})
    assert no_input.status_code == 400

    bad_hash = client.post("/api/verify", json={"hash": "not-a-hash"})
    assert bad_hash.status_code == 400
    assert bad_hash.get_json()["error"]["code"] == "VALIDATION_ERROR"

    unknown = client.post("/api/verify", json={"hash": "f" * 64})
    assert unknown.status_code == 200
    assert unknown.get_json()["data"]["status"] == "not_found"

    detail = client.get("/api/evidence/" + "f" * 64)
    assert detail.status_code == 404


def test_records_and_validation(client):
    for index in range(3):
        response = client.post(
            "/api/evidence",
            data={
                "file": (io.BytesIO(f"record-{index}".encode()), f"f{index}.txt"),
                "user_name": "记录测试",
            },
            content_type="multipart/form-data",
        )
        assert response.status_code == 201

    records = client.get("/api/records?limit=2")
    assert records.status_code == 200
    items = records.get_json()["data"]["items"]
    assert len(items) == 2
    assert items[0]["file_name"] == "f2.txt"

    invalid_limit = client.get("/api/records?limit=0")
    assert invalid_limit.status_code == 400

    non_numeric_limit = client.get("/api/records?limit=abc")
    assert non_numeric_limit.status_code == 400


def test_api_404_is_json(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.is_json
    assert response.get_json()["success"] is False


def test_file_too_large_returns_413(service):
    app = create_app(
        config=make_config(max_content_length=1024, max_file_mb=1),
        service=service,
    )
    client = app.test_client()
    response = client.post(
        "/api/evidence",
        data={
            "file": (io.BytesIO(b"x" * 4096), "too-large.bin"),
            "user_name": "tester",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "FILE_TOO_LARGE"


def test_cors_header(client):
    response = client.options(
        "/api/verify",
        headers={
            "Origin": "http://127.0.0.1:8080",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code in {200, 204}
    allowed_origin = response.headers.get("Access-Control-Allow-Origin")
    assert allowed_origin in {"*", "http://127.0.0.1:8080"}
