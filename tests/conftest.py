import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "ADMIN_PATH", tmp_path / "admin.json")
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def authed_client(client):
    logged = client.post("/api/login", json={"username": "admin", "password": "admin"})
    assert logged.status_code == 200
    changed = client.post(
        "/api/account",
        json={
            "current_password": "admin",
            "username": "keeper",
            "password": "change-me-now",
            "confirm_password": "change-me-now",
        },
    )
    assert changed.status_code == 200
    return client
