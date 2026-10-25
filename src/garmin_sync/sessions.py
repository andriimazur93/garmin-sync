"""Immutable plans, short-lived sessions and idempotent operation results."""
import json
import math
import uuid
from .protocol import ProtocolError, InventoryEntry


def active_session(db, c, session_id):
    row = c.execute('SELECT * FROM sync_sessions WHERE session_id=?', (session_id,)).fetchone()
    if row is None:
        raise ProtocolError(404, 'Unknown session')
    current = c.execute("SELECT value FROM metadata WHERE key='server_id'").fetchone()[0]
    if row['outcome'] is not None or row['expires_at'] <= db.clock() or row['server_id'] != current:
        raise ProtocolError(410, 'Session closed, expired or server identity changed')
    return row


def session_info(db, row):
    return {key: row[key] for key in ('session_id', 'device_epoch', 'server_id', 'protocol_version', 'desired_revision')} | {
        'remaining_seconds': max(0, math.ceil(row['expires_at'] - db.clock()))}


def open_session(db, request):
    body = request.model_dump(mode='json')
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        current = c.execute("SELECT value FROM metadata WHERE key='server_id'").fetchone()[0]
        if body['protocol_version'] != 1 or body['server_id'] != current:
            raise ProtocolError(409, 'Unsupported protocol or server identity')
        old = c.execute('SELECT * FROM sync_sessions WHERE session_id=?', (body['session_id'],)).fetchone()
        if old:
            if any(old[key] != body[key] for key in ('device_epoch', 'server_id', 'protocol_version')):
                raise ProtocolError(409, 'Session UUID reused with conflicting identity')
            return session_info(db, active_session(db, c, body['session_id']))
        if c.execute('SELECT 1 FROM sync_sessions WHERE outcome IS NULL AND expires_at>? AND server_id=?',
                     (db.clock(), current)).fetchone():
            raise ProtocolError(409, 'Another sync session is active')
        c.execute('DELETE FROM inventory_pages WHERE generation_id IN (SELECT g.generation_id FROM inventory_generations g JOIN sync_sessions s USING(session_id) WHERE s.expires_at<=?)', (db.clock(),))
        # Retain expired session UUIDs as tombstones: a delayed retry must not reopen one.
        c.execute('UPDATE sync_sessions SET before_inventory=NULL, after_inventory=NULL, plan=NULL WHERE expires_at<=?',
                  (db.clock(),))
        c.execute('INSERT INTO sync_sessions (session_id,device_epoch,server_id,protocol_version,expires_at) VALUES (?,?,?,?,?)',
                  (body['session_id'], body['device_epoch'], current, 1, db.clock() + 3600))
        association = c.execute('SELECT * FROM association WHERE singleton=1').fetchone()
        if association is None or association['device_epoch'] != body['device_epoch'] or association['server_id'] != current:
            c.execute('INSERT OR REPLACE INTO association VALUES (1,?,?,0)', (body['device_epoch'], current))
        return session_info(db, active_session(db, c, body['session_id']))


def _freeze(db, c, row):
    if row['plan'] is not None:
        return row
    if row['before_inventory'] is None:
        raise ProtocolError(409, 'Complete before inventory required')
    inventory = [InventoryEntry.model_validate(x).model_dump() for x in json.loads(row['before_inventory'])]
    present = {entry['track_id'] for entry in inventory if entry['track_id'] is not None}
    association = c.execute('SELECT * FROM association WHERE singleton=1').fetchone()
    confirmed = association is not None and association['confirmed'] and association['device_epoch'] == row['device_epoch'] and association['server_id'] == row['server_id']
    revision = int(c.execute("SELECT value FROM metadata WHERE key='desired_revision'").fetchone()[0])
    operations = []
    for track in c.execute('SELECT d.track_id,d.present,t.filename,t.size_bytes,t.available FROM desired d JOIN tracks t USING(track_id) ORDER BY d.track_id'):
        tid = track['track_id']
        if track['present'] and track['available'] and tid not in present:
            operations.append({'action': 'download', 'track_id': tid, 'filename': track['filename'],
                               'size_bytes': track['size_bytes'], 'media_path': '/api/v1/media/' + tid})
        elif not track['present'] and confirmed:
            for entry in inventory:
                if entry['track_id'] == tid:
                    operations.append({'action': 'remove', 'track_id': tid, 'cache_id': entry['cache_id']})
    for op in operations:
        op['operation_id'] = str(uuid.uuid5(uuid.UUID(row['session_id']), json.dumps(op, sort_keys=True)))
    c.execute('UPDATE sync_sessions SET desired_revision=?,plan=?,plan_confirmed=? WHERE session_id=?',
              (revision, json.dumps(operations, ensure_ascii=False), int(bool(confirmed)), row['session_id']))
    return active_session(db, c, row['session_id'])


def freeze_plan(db, session_id):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        return session_info(db, _freeze(db, c, active_session(db, c, session_id)))


def plan_page(db, session_id, cursor=None):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = _freeze(db, c, active_session(db, c, session_id))
        items = json.loads(row['plan'])
        index = 0
        if cursor is not None:
            try:
                owner, number = cursor.split(':')
                index = int(number)
                if owner != session_id or index < 0 or index >= len(items):
                    raise ValueError()
            except (ValueError, TypeError):
                raise ProtocolError(409, 'Invalid plan cursor') from None
        count = min(20, len(items) - index)
        while True:
            end = index + count
            page = session_info(db, row) | {'items': items[index:end],
                'total_operations': len(items), 'offset': index, 'association_confirmed': bool(row['plan_confirmed']),
                'next_cursor': f'{session_id}:{end}' if end < len(items) else None}
            if len(json.dumps(page, ensure_ascii=False).encode('utf-8')) <= 8192:
                return page
            count -= 1
            if count <= 0:
                raise ProtocolError(409, 'Plan entry exceeds response budget')


def record_result(db, session_id, operation_id, result):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = active_session(db, c, session_id)
        if row['plan'] is None or operation_id not in {x['operation_id'] for x in json.loads(row['plan'])}:
            raise ProtocolError(409, 'Operation does not belong to this plan')
        payload = result.model_dump_json()
        old = c.execute('SELECT result FROM operation_results WHERE session_id=? AND operation_id=?',
                        (session_id, operation_id)).fetchone()
        if old and old[0] != payload:
            raise ProtocolError(409, 'Conflicting operation result')
        c.execute('INSERT OR IGNORE INTO operation_results VALUES (?,?,?)', (session_id, operation_id, payload))


def finish_session(db, session_id, outcome):
    if outcome not in {'success', 'failed', 'cancelled'}:
        raise ProtocolError(422, 'Invalid finish outcome')
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT * FROM sync_sessions WHERE session_id=?', (session_id,)).fetchone()
        if row and row['outcome'] is not None:
            if row['outcome'] != outcome:
                raise ProtocolError(409, 'Conflicting finish outcome')
            return
        row = active_session(db, c, session_id)
        if outcome == 'success' and (row['plan'] is None or row['after_inventory'] is None):
            raise ProtocolError(409, 'Frozen plan and complete after inventory required')
        c.execute('UPDATE sync_sessions SET outcome=? WHERE session_id=?', (outcome, session_id))


def authorize_media(db, session_id, track_id):
    if not session_id:
        raise ProtocolError(409, 'X-Sync-Session header required')
    with db.connect() as c:
        row = active_session(db, c, session_id)
        if row['plan'] is None:
            raise ProtocolError(409, 'Frozen plan required')
        if not any(op['action'] == 'download' and op['track_id'] == track_id for op in json.loads(row['plan'])):
            raise ProtocolError(403, 'Track is outside this session download plan')
