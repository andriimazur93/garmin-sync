"""Protocol client and isolated, licensed-fixture verification CLI."""
import argparse
import hashlib
import os
from pathlib import Path
import uuid
import httpx


class FakeDevice:
    def __init__(self, client, token, *, cache=None, device_epoch=None):
        self.client = client
        self.headers = {'Authorization': 'Bearer ' + token}
        self.cache = {} if cache is None else cache
        self.device_epoch = device_epoch or str(uuid.uuid4())
        self.pending_session = None

    def _call(self, method, path, **kwargs):
        response = self.client.request(method, path, headers=self.headers, **kwargs)
        response.raise_for_status()
        return response

    def _report(self, sid, phase):
        entries = [{k: entry.get(k) for k in ('track_id', 'cache_id', 'filename')} for entry in self.cache.values()]
        gid = str(uuid.uuid4())
        base = f'/api/v1/sessions/{sid}/inventory/{gid}'
        # Small conservative pages also cover long UTF-8 names in this helper.
        pages = [entries[i:i + 4] for i in range(0, len(entries), 4)]
        for index, page in enumerate(pages):
            self._call('PUT', base + f'/pages/{index}', json={'entries': page})
        self._call('POST', base + '/commit', json={'phase': phase, 'expected_pages': len(pages), 'expected_entries': len(entries)})

    def sync(self, *, before_plan=None, after_plan=None, lose_result_ack=False):
        info = self._call('GET', '/api/v1/info').json()
        if self.pending_session and self.pending_session['server_id'] == info['server_id']:
            response = self.client.post('/api/v1/sessions/' + self.pending_session['session_id'] + '/finish',
                                        json={'outcome': 'cancelled'}, headers=self.headers)
            assert response.status_code in {200, 404, 409, 410}
        sid = str(uuid.uuid4())
        self.pending_session = dict(info, session_id=sid, device_epoch=self.device_epoch)
        self._call('POST', '/api/v1/sessions', json=self.pending_session)
        base = '/api/v1/sessions/' + sid
        self._report(sid, 'before')
        if before_plan:
            before_plan()
        operations, cursor, revision = [], None, None
        while True:
            page = self._call('GET', base + '/plan', params={} if cursor is None else {'cursor': cursor}).json()
            assert page['session_id'] == sid and page['server_id'] == info['server_id']
            assert page['device_epoch'] == self.device_epoch and page['protocol_version'] == 1
            assert page['offset'] == len(operations)
            if revision is None:
                revision = page['desired_revision']
            assert page['desired_revision'] == revision
            operations.extend(page['items'])
            cursor = page['next_cursor']
            if cursor is None:
                assert len(operations) == page['total_operations']
                break
        assert len({op['operation_id'] for op in operations}) == len(operations)
        if after_plan:
            after_plan()
        counts = {'downloads': 0, 'removals': 0}
        for op in sorted(operations, key=lambda item: item['action'] != 'remove'):
            if op['action'] == 'remove':
                assert page['association_confirmed']
                cached = self.cache.get(op['cache_id'])
                if cached:
                    assert cached['track_id'] is not None and cached['track_id'] == op['track_id']
                    del self.cache[op['cache_id']]
                    counts['removals'] += 1
            elif op['action'] == 'download':
                if not any(row['track_id'] == op['track_id'] for row in self.cache.values()):
                    response = self.client.get(op['media_path'], headers=self.headers | {'X-Sync-Session': sid})
                    response.raise_for_status()
                    assert hashlib.sha256(response.content).hexdigest() == op['track_id']
                    cache_id = 'fake-' + op['track_id']
                    self.cache[cache_id] = {'track_id': op['track_id'], 'cache_id': cache_id, 'filename': op['filename']}
                    counts['downloads'] += 1
            else:
                raise AssertionError('Unsupported plan action')
            self._call('PUT', base + '/results/' + op['operation_id'], json={'status': 'success', 'error': None})
            if lose_result_ack:
                raise ConnectionError('Simulated lost result acknowledgement')
        self._report(sid, 'after')
        self._call('POST', base + '/finish', json={'outcome': 'success'})
        self.pending_session = None
        return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8001')
    parser.add_argument('--admin-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    token = os.getenv('GARMIN_SYNC_DEVICE_TOKEN')
    if not token:
        parser.error('Set GARMIN_SYNC_DEVICE_TOKEN through the environment; do not put it in command-line literals')
    fixture = Path(__file__).with_name('fixtures') / 'tone-440hz.mp3'
    track = hashlib.sha256(fixture.read_bytes()).hexdigest()
    try:
        with httpx.Client(base_url=args.base_url, timeout=30) as device_client, httpx.Client(base_url=args.admin_url, timeout=30) as admin:
            catalog = admin.get('/api/local/catalog').json()
            if catalog['next_cursor'] is not None or len(catalog['items']) != 1 or catalog['items'][0]['track_id'] != track or not catalog['items'][0]['available']:
                parser.error('Use isolated server state with only tests/fixtures as its music directory')
            status = admin.get('/api/local/status').json()
            csrf = {'X-CSRF-Token': status['csrf_token']}
            def confirm():
                pair = admin.get('/api/local/status').json()['association']
                admin.post('/api/local/association/confirm', json={k: pair[k] for k in ('server_id', 'device_epoch')}, headers=csrf).raise_for_status()
            admin.put('/api/local/desired/' + track, json={'present': True}, headers=csrf).raise_for_status()
            device = FakeDevice(device_client, token)
            assert device.sync(before_plan=confirm) == {'downloads': 1, 'removals': 0}
            assert device.sync() == {'downloads': 0, 'removals': 0}
            admin.put('/api/local/desired/' + track, json={'present': False}, headers=csrf).raise_for_status()
            assert device.sync() == {'downloads': 0, 'removals': 1}
            assert admin.get('/api/local/status').json()['inventory'] == []
            print('Verified: one fixture download, zero repeat downloads, one removal; final inventory empty.')
    except (httpx.HTTPError, AssertionError, ValueError, KeyError):
        parser.exit(1, 'Fake-device verification failed; inspect local service state. Credentials are redacted.\n')


if __name__ == '__main__':
    main()
