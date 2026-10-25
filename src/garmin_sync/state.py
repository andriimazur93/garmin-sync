"""Owner intent is independent of observed media presence."""
from .protocol import ProtocolError


def set_desired(db, track_id: str, present: bool) -> int:
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM tracks WHERE track_id=?', (track_id,)).fetchone():
            raise ProtocolError(404, 'Unknown track')
        previous = c.execute('SELECT present FROM desired WHERE track_id=?', (track_id,)).fetchone()
        revision = int(c.execute("SELECT value FROM metadata WHERE key='desired_revision'").fetchone()[0])
        if previous is not None and bool(previous[0]) == present:
            return revision
        revision += 1
        c.execute("UPDATE metadata SET value=? WHERE key='desired_revision'", (str(revision),))
        c.execute('INSERT OR REPLACE INTO desired VALUES (?,?,?)', (track_id, int(present), revision))
        return revision


def confirm_association(db, device_epoch: str, server_id: str):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT * FROM association WHERE singleton=1').fetchone()
        current = c.execute("SELECT value FROM metadata WHERE key='server_id'").fetchone()[0]
        if row is None or row['device_epoch'] != device_epoch or row['server_id'] != server_id or server_id != current:
            raise ProtocolError(409, 'Association changed; refresh before confirming')
        c.execute('UPDATE association SET confirmed=1 WHERE singleton=1')
    return {'confirmed': True, 'device_epoch': device_epoch, 'server_id': server_id}
