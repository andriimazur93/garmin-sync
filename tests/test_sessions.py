import json
import uuid
import pytest
from fastapi.testclient import TestClient
from garmin_sync.catalog import scan_catalog, catalog_page
from garmin_sync.db import Database
from garmin_sync.config import Settings
from garmin_sync.admin import create_admin_app
from garmin_sync.device import create_device_app
from garmin_sync.protocol import SessionRequest, OperationResult, ProtocolError
from garmin_sync.state import set_desired, confirm_association
from garmin_sync.sessions import open_session, freeze_plan, plan_page, record_result, finish_session


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / 'music'
    root.mkdir()
    (root / 'song.mp3').write_bytes(b'mp3 fixture')
    now = [1000.0]
    settings = Settings(music_root=root, data_dir=tmp_path / 'data')
    db = Database(settings.database_path, clock=lambda: now[0])
    scan_catalog(db, root)
    track = catalog_page(db, None)['items'][0]['track_id']
    request = SessionRequest(session_id=str(uuid.uuid4()), device_epoch=str(uuid.uuid4()),
                             server_id=db.identity()['server_id'], protocol_version=1)
    return db, root, track, request, now, settings


def before_fixture(db, session_id, entries):
    # A complete committed report fixture. Task 6 tests the real staging/commit API.
    with db.connect() as c:
        c.execute('UPDATE sync_sessions SET before_inventory=? WHERE session_id=?',
                  (json.dumps(entries), session_id))


def begin(setup, entries=()):
    db, _, _, request, _, _ = setup
    open_session(db, request)
    before_fixture(db, str(request.session_id), list(entries))
    return str(request.session_id)


def test_plan_is_immutable_during_browser_changes(setup):
    db, _, track, _, _, _ = setup
    set_desired(db, track, True)
    sid = begin(setup)
    first = plan_page(db, sid, None)
    assert first['items'][0]['action'] == 'download'
    assert first['desired_revision'] == 1
    set_desired(db, track, False)
    assert plan_page(Database(db.path, clock=db.clock), sid, None) == first


def test_duplicate_results_do_not_change_desired(setup):
    db, _, track, _, _, _ = setup
    set_desired(db, track, True)
    sid = begin(setup)
    operation = plan_page(db, sid, None)['items'][0]
    result = OperationResult(status='success')
    record_result(db, sid, operation['operation_id'], result)
    record_result(db, sid, operation['operation_id'], result)
    assert set_desired(db, track, True) == 1
    with pytest.raises(ProtocolError) as exc:
        record_result(db, sid, operation['operation_id'], OperationResult(status='failed', error='network'))
    assert exc.value.status_code == 409
    with db.connect() as c:
        assert c.execute('SELECT count(*) FROM operation_results').fetchone()[0] == 1
        assert c.execute('SELECT before_inventory FROM sync_sessions').fetchone()[0] == '[]'


def test_unknown_cache_entry_is_never_removed(setup):
    db, _, track, request, _, _ = setup
    set_desired(db, track, False)
    sid = begin(setup, [{'track_id': None, 'cache_id': 'unknown', 'filename': 'unknown.mp3'}])
    confirm_association(db, str(request.device_epoch), str(request.server_id))
    assert plan_page(db, sid, None)['items'] == []


def test_new_association_disables_removals(setup):
    db, _, track, request, _, _ = setup
    set_desired(db, track, False)
    entries = [{'track_id': track, 'cache_id': 'mapped', 'filename': 'song.mp3'}]
    sid = begin(setup, entries)
    assert plan_page(db, sid, None)['items'] == []
    assert plan_page(db, sid, None)['association_confirmed'] is False
    confirm_association(db, str(request.device_epoch), str(request.server_id))
    assert plan_page(db, sid, None)['items'] == []  # confirmation cannot mutate frozen plan
    finish_session(db, sid, 'cancelled')
    request.session_id = uuid.uuid4()
    sid = begin(setup, entries)
    item = plan_page(db, sid, None)['items'][0]
    assert item['action'] == 'remove' and item['cache_id'] == 'mapped'
    assert plan_page(db, sid, None)['association_confirmed'] is True
    finish_session(db, sid, 'cancelled')
    request.session_id, request.device_epoch = uuid.uuid4(), uuid.uuid4()
    sid = begin(setup, entries)
    assert plan_page(db, sid, None)['items'] == []


def test_changed_server_requires_reconfirmation(setup):
    db, _, track, request, _, _ = setup
    sid = begin(setup)
    confirm_association(db, str(request.device_epoch), str(request.server_id))
    finish_session(db, sid, 'cancelled')
    with db.connect() as c:
        c.execute("UPDATE metadata SET value=? WHERE key='server_id'", (str(uuid.uuid4()),))
    request.server_id = uuid.UUID(db.identity()['server_id'])
    request.session_id = uuid.uuid4()
    set_desired(db, track, False)
    sid = begin(setup, [{'track_id': track, 'cache_id': 'old', 'filename': None}])
    assert plan_page(db, sid, None)['items'] == []


def test_session_expires_after_3600_seconds(setup):
    db, _, _, request, now, _ = setup
    sid = begin(setup)
    assert open_session(db, request)['remaining_seconds'] == 3600
    now[0] += 3599
    assert plan_page(db, sid, None)['remaining_seconds'] == 1
    now[0] += 1
    with pytest.raises(ProtocolError) as exc:
        plan_page(db, sid, None)
    assert exc.value.status_code == 410
    with pytest.raises(ProtocolError):
        open_session(db, request)  # expired UUID cannot create a new session
    request.session_id = uuid.uuid4()
    assert open_session(db, request)['remaining_seconds'] == 3600


def test_unavailable_source_does_not_request_removal(setup):
    db, root, track, _, _, _ = setup
    set_desired(db, track, True)
    (root / 'song.mp3').unlink()
    scan_catalog(db, root)
    sid = begin(setup, [{'track_id': track, 'cache_id': 'offline', 'filename': 'song.mp3'}])
    assert plan_page(db, sid, None)['items'] == []


def test_session_conflicts_replay_and_finish(setup):
    db, _, _, request, _, _ = setup
    first = open_session(db, request)
    assert open_session(db, request) == first
    other = request.model_copy(update={'session_id': uuid.uuid4()})
    with pytest.raises(ProtocolError) as exc:
        open_session(db, other)
    assert exc.value.status_code == 409
    with pytest.raises(ProtocolError):
        open_session(db, request.model_copy(update={'device_epoch': uuid.uuid4()}))
    with pytest.raises(ProtocolError):
        open_session(db, request.model_copy(update={'protocol_version': 2}))
    finish_session(db, str(request.session_id), 'cancelled')
    finish_session(db, str(request.session_id), 'cancelled')
    with pytest.raises(ProtocolError):
        finish_session(db, str(request.session_id), 'failed')
    assert open_session(db, other)['session_id'] == str(other.session_id)


def test_incomplete_inventory_cannot_generate_plan(setup):
    db, _, _, request, _, _ = setup
    open_session(db, request)
    with pytest.raises(ProtocolError) as exc:
        freeze_plan(db, str(request.session_id))
    assert exc.value.status_code == 409


def test_plan_pages_are_bounded_stable_and_complete(setup):
    db, root, _, _, _, _ = setup
    for i in range(55):
        (root / (str(i) + '界' * 70 + '.mp3')).write_bytes(str(i).encode())
    scan_catalog(db, root)
    with db.connect() as c:
        tracks = [r[0] for r in c.execute('SELECT track_id FROM tracks')]
    for track in tracks:
        set_desired(db, track, True)
    sid = begin(setup)
    cursor, items = None, []
    while True:
        page = plan_page(db, sid, cursor)
        assert len(page['items']) <= 20
        assert len(json.dumps(page, ensure_ascii=False).encode()) <= 8192
        items.extend(page['items'])
        cursor = page['next_cursor']
        if cursor is None:
            break
    assert len(items) == len(tracks)
    assert len({op['operation_id'] for op in items}) == len(tracks)
    with pytest.raises(ProtocolError):
        plan_page(db, sid, str(uuid.uuid4()) + ':1')


def test_session_http_and_local_association_boundary(setup):
    db, _, track, request, _, settings = setup
    client = TestClient(create_device_app(settings))
    admin = TestClient(create_admin_app(settings), base_url='http://127.0.0.1:8000')
    headers = {'Authorization': 'Bearer ' + db.identity()['device_token']}
    body = request.model_dump(mode='json')
    assert client.post('/api/v1/sessions', json=body).status_code == 401
    assert client.post('/api/v1/sessions', json=body, headers=headers).status_code == 200
    assert client.post('/api/v1/sessions', json=body | {'protocol_version': 2}, headers=headers).status_code == 409
    csrf = {'X-CSRF-Token': db.identity()['csrf_token']}
    url = '/api/local/desired/' + track
    assert admin.put(url, json={'present': True}).status_code == 403
    assert admin.put(url, json={'present': True}, headers=csrf).json()['desired_revision'] == 1
    association = {'server_id': body['server_id'], 'device_epoch': body['device_epoch']}
    assert client.post('/api/local/association/confirm', json=association, headers=headers).status_code == 404
    assert admin.post('/api/local/association/confirm', json=association, headers=csrf).status_code == 200
    assert admin.post('/api/local/association/confirm', json=association | {'device_epoch': str(uuid.uuid4())}, headers=csrf).status_code == 409
