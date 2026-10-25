import pytest
from garmin_sync.catalog import scan_catalog, catalog_page
from garmin_sync.db import Database
from garmin_sync.protocol import ProtocolError
from garmin_sync.state import set_desired


def test_same_desired_value_is_noop(tmp_path):
    db = Database(tmp_path / 'state.db')
    root = tmp_path / 'music'
    root.mkdir()
    (root / 'one.mp3').write_bytes(b'one')
    scan_catalog(db, root)
    track = catalog_page(db, None)['items'][0]['track_id']
    assert set_desired(db, track, True) == 1
    assert set_desired(db, track, True) == 1
    assert set_desired(db, track, False) == 2
    assert set_desired(Database(db.path), track, False) == 2
    assert (root / 'one.mp3').read_bytes() == b'one'
    with pytest.raises(ProtocolError) as exc:
        set_desired(db, 'a' * 64, True)
    assert exc.value.status_code == 404
