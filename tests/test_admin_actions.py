from fastapi.testclient import TestClient
from garmin_sync.admin import create_admin_app
from garmin_sync.device import create_device_app
from garmin_sync.config import Settings


def test_management_assets_are_local_and_have_no_inline_script(tmp_path):
    settings = Settings(music_root=tmp_path / 'music', data_dir=tmp_path / 'data')
    admin = TestClient(create_admin_app(settings), base_url='http://127.0.0.1:8000')
    page = admin.get('/')
    assert page.status_code == 200
    assert 'Garmin Sync' in page.text and '/static/app.js' in page.text
    assert "frame-ancestors 'none'" in page.headers['content-security-policy']
    assert admin.get('/static/app.js').status_code == 200
    assert admin.get('/static/style.css').status_code == 200
    assert admin.get('/static/../../db.py').status_code == 404
    device = TestClient(create_device_app(settings))
    assert device.get('/').status_code == 404 and device.get('/static/app.js').status_code == 404


def test_admin_rejects_invalid_boolean_and_unsafe_origin(tmp_path):
    root = tmp_path / 'music'; root.mkdir()
    (root / '<img onerror=alert(1)>.mp3').write_bytes(b'fixture')
    admin = TestClient(create_admin_app(Settings(music_root=root, data_dir=tmp_path / 'data')), base_url='http://127.0.0.1:8000')
    status = admin.get('/api/local/status').json()
    track = status['tracks'][0]['track_id']
    headers = {'X-CSRF-Token': status['csrf_token']}
    assert admin.put('/api/local/desired/' + track, json={'present': 'false'}, headers=headers).status_code == 422
    assert admin.put('/api/local/desired/' + track, json={'present': True}, headers=headers | {'Origin': 'http://attacker.test'}).status_code == 403
    assert admin.get('/api/local/status').json()['tracks'][0]['desired'] is None
