"""Publish complete generations atomically; never infer inventory from results."""
from datetime import datetime, timezone
import json
import uuid
from pydantic import ValidationError
from .protocol import InventoryEntry, ProtocolError
from .sessions import active_session


def _generation(c, session_id, generation_id):
    try:
        if str(uuid.UUID(generation_id)) != generation_id:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ProtocolError(422, 'Invalid generation UUID') from None
    row = c.execute('SELECT * FROM inventory_generations WHERE generation_id=?', (generation_id,)).fetchone()
    if row is not None and row['session_id'] != session_id:
        raise ProtocolError(409, 'Generation belongs to another session')
    if row is None:
        c.execute('INSERT INTO inventory_generations (generation_id,session_id) VALUES (?,?)', (generation_id, session_id))
        row = c.execute('SELECT * FROM inventory_generations WHERE generation_id=?', (generation_id,)).fetchone()
    return row


def stage_inventory_page(db, session_id, generation_id, page_number, entries):
    if not isinstance(page_number, int) or not 0 <= page_number < 4096 or len(entries) > 20:
        raise ProtocolError(422, 'Invalid inventory page number or count')
    try:
        entries = [InventoryEntry.model_validate(entry).model_dump() for entry in entries]
    except ValidationError:
        raise ProtocolError(422, 'Invalid inventory entry') from None
    encoded = json.dumps({'entries': entries}, ensure_ascii=False)
    if len(encoded.encode('utf-8')) > 8192:
        raise ProtocolError(413, 'Inventory page exceeds byte budget')
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True)
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        active_session(db, c, session_id)
        gen = _generation(c, session_id, generation_id)
        old = c.execute('SELECT entries FROM inventory_pages WHERE generation_id=? AND page_number=?',
                        (generation_id, page_number)).fetchone()
        if old:
            if old[0] != payload:
                raise ProtocolError(409, 'Conflicting inventory page retry')
            return
        if gen['report'] is not None:
            raise ProtocolError(409, 'Generation already committed')
        c.execute('INSERT INTO inventory_pages VALUES (?,?,?)', (generation_id, page_number, payload))


def commit_inventory(db, session_id, generation_id, phase, expected_pages, expected_entries):
    if phase not in {'before', 'after'} or not 0 <= expected_pages <= 4096 or not 0 <= expected_entries <= expected_pages * 20:
        raise ProtocolError(422, 'Invalid inventory completion marker')
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        session = active_session(db, c, session_id)
        gen = _generation(c, session_id, generation_id)
        if gen['report'] is not None:
            saved = json.loads(gen['report'])
            if saved['phase'] != phase or saved['pages'] != expected_pages or saved['entries'] != expected_entries:
                raise ProtocolError(409, 'Conflicting inventory commit retry')
            return saved
        if session[phase + '_inventory'] is not None:
            raise ProtocolError(409, 'This inventory phase is already committed')
        if phase == 'after' and (session['before_inventory'] is None or session['plan'] is None):
            raise ProtocolError(409, 'Before inventory and frozen plan required first')
        previous = c.execute('SELECT generation_seq FROM latest_inventory WHERE singleton=1').fetchone()
        if previous and previous[0] >= gen['sequence']:
            raise ProtocolError(409, 'Stale inventory generation')
        pages = c.execute('SELECT page_number,entries FROM inventory_pages WHERE generation_id=? ORDER BY page_number',
                          (generation_id,)).fetchall()
        if [p['page_number'] for p in pages] != list(range(expected_pages)):
            raise ProtocolError(409, 'Inventory pages are incomplete')
        entries = [entry for page in pages for entry in json.loads(page['entries'])]
        if len(entries) != expected_entries or len({e['cache_id'] for e in entries}) != len(entries):
            raise ProtocolError(409, 'Inventory count mismatch or duplicate cache references')
        reported_at = datetime.fromtimestamp(db.clock(), timezone.utc).isoformat()
        report = {'generation_id': generation_id, 'session_id': session_id, 'phase': phase,
                  'pages': expected_pages, 'entries': expected_entries, 'reported_at': reported_at,
                  'device_epoch': session['device_epoch'], 'server_id': session['server_id']}
        payload = json.dumps(entries, ensure_ascii=False)
        c.execute('UPDATE inventory_generations SET report=? WHERE generation_id=?', (json.dumps(report), generation_id))
        # Column selection is a validated enum, never a request-provided SQL identifier.
        c.execute(f'UPDATE sync_sessions SET {phase}_inventory=? WHERE session_id=?', (payload, session_id))
        c.execute('INSERT OR REPLACE INTO latest_inventory VALUES (1,?,?,?)', (gen['sequence'], json.dumps(report), payload))
        for entry in entries:
            if entry['track_id'] is not None:
                c.execute('INSERT OR IGNORE INTO tracks VALUES (?,?,0,0,?)',
                          (entry['track_id'], entry['filename'] or entry['track_id'], ''))
        return report


def get_status(db):
    with db.connect() as c:
        c.execute('BEGIN')
        last = c.execute('SELECT * FROM latest_inventory WHERE singleton=1').fetchone()
        report = json.loads(last['report']) if last else None
        entries = json.loads(last['entries']) if last else None
        observed = {e['track_id'] for e in entries or [] if e['track_id'] is not None}
        errors = {}
        sessions = c.execute('SELECT rowid,* FROM sync_sessions ORDER BY rowid DESC').fetchall()
        for session in sessions:
            if session['plan'] is None:
                continue
            operations = {op['operation_id']: op for op in json.loads(session['plan'])}
            for result in c.execute('SELECT * FROM operation_results WHERE session_id=?', (session['session_id'],)):
                op = operations.get(result['operation_id'])
                if op and op['track_id'] not in errors:
                    body = json.loads(result['result'])
                    errors[op['track_id']] = body['error'] if body['status'] == 'failed' else None
        tracks = []
        for row in c.execute('SELECT t.*,d.present FROM tracks t LEFT JOIN desired d USING(track_id) ORDER BY t.filename,t.track_id'):
            present = bool(row['present']) if row['present'] is not None else None
            on_watch = row['track_id'] in observed if entries is not None else None
            tracks.append({'track_id': row['track_id'], 'filename': row['filename'],
                           'size_bytes': row['size_bytes'], 'available': bool(row['available']),
                           'desired': present, 'observed': on_watch,
                           'pending_download': present is True and on_watch is not True,
                           'pending_removal': present is False and on_watch is not False,
                           'last_error': errors.get(row['track_id'])})
        association = c.execute('SELECT device_epoch,server_id,confirmed FROM association WHERE singleton=1').fetchone()
        association = dict(association) if association else None
        if association:
            current = c.execute("SELECT value FROM metadata WHERE key='server_id'").fetchone()[0]
            association['confirmed'] = bool(association['confirmed']) and association['server_id'] == current
        latest_sync = None
        if sessions:
            session = sessions[0]
            outcome = session['outcome'] or ('expired' if session['expires_at'] <= db.clock() else 'in_progress')
            latest_sync = {'session_id': session['session_id'], 'outcome': outcome}
        revision = int(c.execute("SELECT value FROM metadata WHERE key='desired_revision'").fetchone()[0])
        return {'inventory': entries, 'reported_at': report['reported_at'] if report else None,
                'inventory_report': report, 'tracks': tracks, 'desired_revision': revision,
                'association': association, 'latest_sync': latest_sync}
