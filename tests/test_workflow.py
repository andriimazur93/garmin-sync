from pathlib import Path
import shutil
import pytest
from fastapi.testclient import TestClient
from garmin_sync.config import Settings
from garmin_sync.admin import create_admin_app
from garmin_sync.device import create_device_app
from tests.fake_device import FakeDevice


@pytest.fixture
def workflow(tmp_path):
    root = tmp_path / 'music'; root.mkdir()
    fixture = Path(__file__).parent / 'fixtures/tone-440hz.mp3'
    shutil.copyfile(fixture, root / 'song.mp3')
    settings = Settings(music_root=root, data_dir=tmp_path / 'data')
    admin = TestClient(create_admin_app(settings), base_url='http://127.0.0.1:8000')
    app = create_device_app(settings)
    device = FakeDevice(TestClient(app), app.state.db.identity()['device_token'])
    return settings, admin, device, fixture.read_bytes()


def choose(admin, track, present):
    csrf = admin.get('/api/local/status').json()['csrf_token']
    response = admin.put('/api/local/desired/' + track, json={'present': present}, headers={'X-CSRF-Token': csrf})
    response.raise_for_status()


def confirm(admin):
    status = admin.get('/api/local/status').json()
    pair = {key: status['association'][key] for key in ('server_id', 'device_epoch')}
    response = admin.post('/api/local/association/confirm', json=pair, headers={'X-CSRF-Token': status['csrf_token']})
    response.raise_for_status()


def test_complete_download_repeat_and_removal_workflow(workflow):
    settings, admin, device, original = workflow
    track = admin.get('/api/local/catalog').json()['items'][0]['track_id']
    assert admin.get('/api/local/status').json()['inventory'] is None
    choose(admin, track, True)
    assert admin.get('/api/local/status').json()['tracks'][0]['pending_download'] is True
    first = device.sync(before_plan=lambda: confirm(admin))
    assert first == {'downloads': 1, 'removals': 0}
    status = admin.get('/api/local/status').json()
    assert status['tracks'][0]['observed'] is True and status['tracks'][0]['pending_download'] is False
    assert device.sync() == {'downloads': 0, 'removals': 0}
    choose(admin, track, False)
    assert device.sync() == {'downloads': 0, 'removals': 1}
    status = admin.get('/api/local/status').json()
    assert status['inventory'] == [] and status['tracks'][0]['observed'] is False
    assert (settings.music_root / 'song.mp3').read_bytes() == original


def test_changed_browser_choice_waits_for_next_sync(workflow):
    _, admin, device, _ = workflow
    track = admin.get('/api/local/catalog').json()['items'][0]['track_id']
    choose(admin, track, True)
    device.sync(before_plan=lambda: confirm(admin), after_plan=lambda: choose(admin, track, False))
    status = admin.get('/api/local/status').json()
    assert status['tracks'][0]['observed'] and status['tracks'][0]['pending_removal']
    assert device.sync()['removals'] == 1


def test_lost_result_response_and_server_restart_do_not_redownload(workflow):
    settings, admin, device, _ = workflow
    track = admin.get('/api/local/catalog').json()['items'][0]['track_id']
    choose(admin, track, True)
    with pytest.raises(ConnectionError):
        device.sync(lose_result_ack=True)
    assert len(device.cache) == 1
    assert admin.get('/api/local/status').json()['inventory'] == []  # before report only
    new_app = create_device_app(settings)
    device.client = TestClient(new_app)
    assert device.sync() == {'downloads': 0, 'removals': 0}
    assert admin.get('/api/local/status').json()['tracks'][0]['observed'] is True


def test_unavailable_source_and_unknown_entries_remain_visible(workflow):
    settings, admin, device, _ = workflow
    track = admin.get('/api/local/catalog').json()['items'][0]['track_id']
    choose(admin, track, True)
    device.sync(before_plan=lambda: confirm(admin))
    device.cache['unknown'] = {'track_id': None, 'cache_id': 'unknown', 'filename': '<unknown>.mp3'}
    (settings.music_root / 'song.mp3').unlink()
    csrf = admin.get('/api/local/status').json()['csrf_token']
    admin.post('/api/local/rescan', headers={'X-CSRF-Token': csrf}).raise_for_status()
    assert device.sync() == {'downloads': 0, 'removals': 0}
    status = admin.get('/api/local/status').json()
    assert status['tracks'][0]['observed'] is True and status['tracks'][0]['available'] is False
    assert len(status['inventory']) == 2
    choose(admin, track, False)
    assert device.sync()['removals'] == 1
    assert list(device.cache) == ['unknown']
