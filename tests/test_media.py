from fastapi.testclient import TestClient
from garmin_sync.config import Settings
from garmin_sync.db import Database
from garmin_sync.catalog import scan_catalog, catalog_page
from garmin_sync.device import create_device_app


def test_range_response_matches_source(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    (root / "sample.mp3").write_bytes(b"0123456789")
    settings = Settings(music_root=root, data_dir=tmp_path / "data")
    client = TestClient(create_device_app(settings))
    db = Database(settings.database_path)
    scan_catalog(db, root)
    track = catalog_page(db, None)["items"][0]["track_id"]
    url = "/api/v1/media/" + track
    headers = {"Authorization": "Bearer " + db.identity()["device_token"]}
    assert client.get(url).status_code == 401
    import uuid
    from garmin_sync.protocol import SessionRequest
    from garmin_sync.sessions import open_session, plan_page
    from garmin_sync.state import set_desired
    from tests.test_sessions import before_fixture
    request = SessionRequest(session_id=uuid.uuid4(), device_epoch=uuid.uuid4(),
                             server_id=db.identity()['server_id'], protocol_version=1)
    open_session(db, request)
    sid = str(request.session_id)
    set_desired(db, track, True)
    before_fixture(db, sid, [])
    plan_page(db, sid, None)
    headers['X-Sync-Session'] = sid
    response = client.get(url, headers=headers | {"Range": "bytes=2-5"})
    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["content-length"] == "4"
    assert response.headers["content-type"] == "audio/mpeg"
    assert client.get(url, headers=headers | {"Range": "bytes=-3"}).content == b"789"
    assert client.get(url, headers=headers | {"Range": "bytes=11-"}).status_code == 416
    assert client.get(url, headers=headers).content == b"0123456789"
    assert client.get("/api/v1/media/../../etc/passwd", headers=headers).status_code in {401, 404}


def test_media_requires_active_session_and_planned_track(tmp_path):
    import uuid
    from garmin_sync.protocol import SessionRequest
    from garmin_sync.sessions import open_session, finish_session, plan_page
    from garmin_sync.state import set_desired
    from tests.test_sessions import before_fixture
    root = tmp_path / 'music'
    root.mkdir()
    (root / 'sample.mp3').write_bytes(b'0123456789')
    settings = Settings(music_root=root, data_dir=tmp_path / 'data')
    client = TestClient(create_device_app(settings))
    db = Database(settings.database_path)
    scan_catalog(db, root)
    track = catalog_page(db, None)['items'][0]['track_id']
    request = SessionRequest(session_id=uuid.uuid4(), device_epoch=uuid.uuid4(),
                             server_id=db.identity()['server_id'], protocol_version=1)
    open_session(db, request)
    sid = str(request.session_id)
    headers = {'Authorization': 'Bearer ' + db.identity()['device_token']}
    url = '/api/v1/media/' + track
    assert client.get(url, headers=headers).status_code == 409
    assert client.get(url, headers=headers | {'X-Sync-Session': str(uuid.uuid4())}).status_code == 404
    headers['X-Sync-Session'] = sid
    assert client.get(url, headers=headers).status_code == 409  # not frozen
    set_desired(db, track, True)
    before_fixture(db, sid, [])
    plan_page(db, sid, None)
    assert client.get(url, headers=headers).content == b'0123456789'
    assert client.head(url, headers=headers).headers['content-length'] == '10'
    (root / 'sample.mp3').write_bytes(b'changed')
    assert client.get(url, headers=headers).status_code == 404
    finish_session(db, sid, 'cancelled')
    assert client.get(url, headers=headers).status_code == 410


def test_media_rejects_unplanned_tracks_and_expired_sessions(tmp_path):
    import uuid
    from garmin_sync.protocol import SessionRequest
    from garmin_sync.sessions import open_session, plan_page
    from tests.test_sessions import before_fixture
    root = tmp_path / 'music'
    root.mkdir()
    (root / 'sample.mp3').write_bytes(b'0123456789')
    settings = Settings(music_root=root, data_dir=tmp_path / 'data')
    app = create_device_app(settings)
    db = app.state.db
    now = [1000.0]
    db.clock = lambda: now[0]
    scan_catalog(db, root)
    track = catalog_page(db, None)['items'][0]['track_id']
    request = SessionRequest(session_id=uuid.uuid4(), device_epoch=uuid.uuid4(),
                             server_id=db.identity()['server_id'], protocol_version=1)
    open_session(db, request)
    sid = str(request.session_id)
    before_fixture(db, sid, [])
    plan_page(db, sid, None)
    headers = {'Authorization': 'Bearer ' + db.identity()['device_token'], 'X-Sync-Session': sid}
    client = TestClient(app)
    assert client.get('/api/v1/media/' + track, headers=headers).status_code == 403
    now[0] += 3600
    assert client.get('/api/v1/media/' + track, headers=headers).status_code == 410
