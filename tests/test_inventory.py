import uuid
import pytest
from fastapi.testclient import TestClient
from garmin_sync.protocol import ProtocolError
from garmin_sync.sessions import open_session, plan_page, finish_session
from garmin_sync.inventory import stage_inventory_page, commit_inventory, get_status
from garmin_sync.device import create_device_app
from tests.test_sessions import setup  # shared deterministic database/clock fixture


def generation():
    return str(uuid.uuid4())


def start(setup):
    db, _, track, request, _, _ = setup
    open_session(db, request)
    return db, str(request.session_id), {'track_id': track, 'cache_id': 'cache-1', 'filename': 'song.mp3'}


def report(db, sid, entries, phase='before'):
    gid = generation()
    if entries:
        stage_inventory_page(db, sid, gid, 0, entries)
    return commit_inventory(db, sid, gid, phase, int(bool(entries)), len(entries))


def test_partial_report_preserves_previous_inventory(setup):
    db, sid, entry = start(setup)
    previous = report(db, sid, [entry])
    plan_page(db, sid, None)
    setup[4][0] += 30
    gid = generation()
    stage_inventory_page(db, sid, gid, 0, [{'track_id': None, 'cache_id': 'new', 'filename': None}])
    with pytest.raises(ProtocolError):
        commit_inventory(db, sid, gid, 'after', 2, 2)
    assert get_status(db)['inventory'] == [entry]
    assert get_status(db)['reported_at'] == previous['reported_at']
    commit_inventory(db, sid, gid, 'after', 1, 1)
    assert get_status(db)['reported_at'] != previous['reported_at']


def test_empty_report_requires_explicit_commit(setup):
    db, sid, _ = start(setup)
    assert get_status(db)['inventory'] is None
    result = report(db, sid, [])
    assert result['entries'] == 0
    assert get_status(db)['inventory'] == []
    assert get_status(db)['reported_at'] is not None
    plan_page(db, sid, None)
    with pytest.raises(ProtocolError):
        finish_session(db, sid, 'success')
    report(db, sid, [], 'after')
    finish_session(db, sid, 'success')


def test_duplicate_page_is_idempotent(setup):
    db, sid, entry = start(setup)
    gid = generation()
    stage_inventory_page(db, sid, gid, 0, [entry])
    stage_inventory_page(db, sid, gid, 0, [entry])
    first = commit_inventory(db, sid, gid, 'before', 1, 1)
    setup[4][0] += 20
    assert commit_inventory(db, sid, gid, 'before', 1, 1) == first
    stage_inventory_page(db, sid, gid, 0, [entry])
    assert get_status(db)['reported_at'] == first['reported_at']


def test_conflicting_page_is_rejected(setup):
    db, sid, entry = start(setup)
    gid = generation()
    stage_inventory_page(db, sid, gid, 0, [entry])
    with pytest.raises(ProtocolError) as exc:
        stage_inventory_page(db, sid, gid, 0, [])
    assert exc.value.status_code == 409
    commit_inventory(db, sid, gid, 'before', 1, 1)
    with pytest.raises(ProtocolError):
        commit_inventory(db, sid, gid, 'before', 1, 2)
    with pytest.raises(ProtocolError):
        stage_inventory_page(db, sid, gid, 1, [entry])


def test_old_generation_cannot_replace_new_report(setup):
    db, sid, entry = start(setup)
    old, new = generation(), generation()
    stage_inventory_page(db, sid, old, 0, [entry])
    stage_inventory_page(db, sid, new, 0, [entry])
    commit_inventory(db, sid, new, 'before', 1, 1)
    plan_page(db, sid, None)
    after = report(db, sid, [], 'after')
    with pytest.raises(ProtocolError):
        commit_inventory(db, sid, old, 'before', 1, 1)
    # Retry of a formerly valid before commit must not republish over after.
    commit_inventory(db, sid, new, 'before', 1, 1)
    assert get_status(db)['inventory'] == []
    assert get_status(db)['reported_at'] == after['reported_at']


def test_counts_holes_duplicate_cache_ids_and_phase_are_validated(setup):
    db, sid, entry = start(setup)
    gid = generation()
    stage_inventory_page(db, sid, gid, 1, [entry])
    with pytest.raises(ProtocolError):
        commit_inventory(db, sid, gid, 'before', 2, 1)
    stage_inventory_page(db, sid, gid, 0, [entry])
    with pytest.raises(ProtocolError):
        commit_inventory(db, sid, gid, 'before', 2, 2)
    with pytest.raises(ProtocolError):
        report(db, sid, [], 'after')  # after requires before and plan
    assert get_status(db)['inventory'] is None


def test_expired_upload_cleanup_keeps_last_report(setup):
    db, sid, entry = start(setup)
    previous = report(db, sid, [entry])
    gid = generation()
    stage_inventory_page(db, sid, gid, 0, [entry])
    setup[4][0] += 3600
    with pytest.raises(ProtocolError) as exc:
        commit_inventory(db, sid, gid, 'after', 1, 1)
    assert exc.value.status_code == 410
    request = setup[3]
    request.session_id = uuid.uuid4()
    open_session(db, request)
    with db.connect() as c:
        assert c.execute('SELECT count(*) FROM inventory_pages WHERE generation_id=?', (gid,)).fetchone()[0] == 0
    assert get_status(db)['reported_at'] == previous['reported_at']
    assert get_status(db)['inventory'] == [entry]


def test_inventory_http_limits_and_commit(setup):
    db, _, track, request, _, settings = setup
    app = create_device_app(settings)
    client = TestClient(app)
    headers = {'Authorization': 'Bearer ' + db.identity()['device_token']}
    body = request.model_dump(mode='json')
    client.post('/api/v1/sessions', json=body, headers=headers).raise_for_status()
    base = '/api/v1/sessions/' + str(request.session_id) + '/inventory/'
    gid = generation()
    entry = {'track_id': track, 'cache_id': 'cache-1', 'filename': 'song.mp3'}
    url = base + gid + '/pages/0'
    assert client.put(url, json={'entries': [entry]}).status_code == 401
    assert client.put(url, json={'entries': [entry] * 21}, headers=headers).status_code == 422
    assert client.put(url, content=b' ' * 8193, headers=headers | {'Content-Type': 'application/json'}).status_code == 413
    assert client.put(url, json={'entries': [entry]}, headers=headers).status_code == 200
    assert client.post(base + gid + '/commit', json={'phase': 'before', 'expected_pages': 1, 'expected_entries': 1}, headers=headers).status_code == 200
    page = client.get('/api/v1/sessions/' + str(request.session_id) + '/plan', headers=headers)
    assert page.status_code == 200
