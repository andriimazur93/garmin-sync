from garmin_sync.config import Settings
from garmin_sync.db import Database
from garmin_sync.admin import create_admin_app
from garmin_sync.device import create_device_app
from fastapi.testclient import TestClient


def test_init_preserves_server_identity_and_token(tmp_path):
    first = Database(tmp_path / "state.db")
    second = Database(tmp_path / "state.db")
    assert first.identity() == second.identity()
    assert len(first.identity()["device_token"]) >= 40
    assert (tmp_path / "state.db").stat().st_mode & 0o077 == 0


def test_services_share_state_without_sharing_routes(tmp_path):
    settings = Settings(music_root=tmp_path / "music", data_dir=tmp_path / "data")
    admin = TestClient(create_admin_app(settings), base_url="http://127.0.0.1:8000")
    device = TestClient(create_device_app(settings))
    assert admin.get("/health").json() == {"status": "ok"}
    assert device.get("/health").json() == {"status": "ok"}
    token = Database(settings.database_path).identity()["device_token"]
    info = device.get("/api/v1/info", headers={"Authorization": f"Bearer {token}"})
    assert info.status_code == 200
    assert info.json()["protocol_version"] == 1
