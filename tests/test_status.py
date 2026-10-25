import uuid
from garmin_sync.db import Database
from garmin_sync.catalog import scan_catalog
from garmin_sync.sessions import plan_page, record_result, finish_session
from garmin_sync.state import set_desired
from garmin_sync.protocol import OperationResult
from garmin_sync.inventory import get_status
from tests.test_sessions import setup
from tests.test_inventory import start, report


def test_no_inventory_means_unknown(setup):
    db, _, track, _, _, _ = setup
    status = get_status(db)
    assert status['inventory'] is None and status['reported_at'] is None
    assert status['tracks'][0]['observed'] is None
    set_desired(db, track, True)
    status = get_status(db)
    assert status['tracks'][0]['pending_download'] is True
    assert status['tracks'][0]['observed'] is None


def test_offline_only_track_remains_visible(setup):
    db, root, track, _, _, _ = setup
    db, sid, entry = start(setup)
    unknown = {'track_id': None, 'cache_id': 'unmapped', 'filename': 'old.mp3'}
    recovered = {'track_id': 'a' * 64, 'cache_id': 'recovered', 'filename': 'offline-only.mp3'}
    report(db, sid, [entry, unknown, recovered])
    (root / 'song.mp3').unlink()
    scan_catalog(db, root)
    status = get_status(Database(db.path, clock=db.clock))
    assert status['inventory'] == [entry, unknown, recovered]
    tracks = {t['track_id']: t for t in status['tracks']}
    assert tracks[track]['observed'] is True and tracks[track]['available'] is False
    assert tracks['a' * 64]['filename'] == 'offline-only.mp3'
    assert set_desired(db, 'a' * 64, False) == 1
    assert get_status(db)['tracks'][0]['pending_removal'] or get_status(db)['tracks'][1]['pending_removal']


def test_results_do_not_claim_downloaded_or_erase_report_time(setup):
    db, _, track, _, now, _ = setup
    set_desired(db, track, True)
    db, sid, _ = start(setup)
    previous = report(db, sid, [])
    op = plan_page(db, sid, None)['items'][0]
    record_result(db, sid, op['operation_id'], OperationResult(status='failed', error='outage'))
    now[0] += 20
    status = get_status(db)
    assert status['tracks'][0]['last_error'] == 'outage'
    assert status['tracks'][0]['observed'] is False
    assert status['tracks'][0]['pending_download'] is True
    assert status['reported_at'] == previous['reported_at']
    finish_session(db, sid, 'failed')
    assert get_status(db)['latest_sync']['outcome'] == 'failed'
