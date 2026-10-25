import pytest
from fastapi.testclient import TestClient
from garmin_sync.config import Settings
from garmin_sync.db import Database
from garmin_sync.admin import create_admin_app
from garmin_sync.device import create_device_app


@pytest.fixture
def settings(tmp_path):
    return Settings(music_root=tmp_path / "music", data_dir=tmp_path / "data")


def test_device_app_excludes_admin_routes(settings):
    device = TestClient(create_device_app(settings))
    token = Database(settings.database_path).identity()["device_token"]
    assert device.get("/api/local/status", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert device.get("/").status_code == 404


@pytest.mark.parametrize("header", [None, "Bearer wrong", "Basic abc"])
def test_invalid_device_token_is_rejected(settings, header):
    device = TestClient(create_device_app(settings))
    headers = {} if header is None else {"Authorization": header}
    assert device.get("/api/v1/info", headers=headers).status_code == 401


def test_admin_rejects_untrusted_host_and_origin(settings):
    admin = TestClient(create_admin_app(settings), base_url="http://127.0.0.1:8000")
    assert admin.get("/api/local/status", headers={"Host": "attacker.example"}).status_code == 400
    assert admin.post("/api/local/rescan", headers={"Origin": "https://attacker.example"}).status_code == 403
    assert admin.post("/api/local/rescan").status_code == 403
    token = admin.get("/api/local/status").json()["csrf_token"]
    response = admin.post("/api/local/rescan", headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": token})
    assert response.status_code == 200
