import hashlib
import os
import json
import pytest
from garmin_sync.db import Database
from garmin_sync.catalog import scan_catalog, catalog_page, resolve_track, CatalogError


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    return Database(tmp_path / "state.db"), root


def test_rename_keeps_digest_id(library):
    db, root = library
    file = root / "track.mp3"
    file.write_bytes(b"audio bytes")
    scan_catalog(db, root)
    original = catalog_page(db, None)["items"][0]["track_id"]
    file.rename(root / "renamed.mp3")
    scan_catalog(db, root)
    assert catalog_page(db, None)["items"][0]["track_id"] == original
    assert original == hashlib.sha256(b"audio bytes").hexdigest()


def test_replacement_cannot_serve_old_id(library):
    db, root = library
    file = root / "track.mp3"
    file.write_bytes(b"old")
    scan_catalog(db, root)
    track = catalog_page(db, None)["items"][0]["track_id"]
    file.write_bytes(b"new")
    with pytest.raises(CatalogError):
        resolve_track(db, track)
    scan_catalog(db, root)
    assert resolve_track(db, hashlib.sha256(b"new").hexdigest()).read() == b"new"


def test_symlink_escape_is_rejected(library, tmp_path):
    db, root = library
    outside = tmp_path / "private.mp3"
    outside.write_bytes(b"private")
    (root / "escape.mp3").symlink_to(outside)
    scan_catalog(db, root)
    assert catalog_page(db, None)["items"] == []


def test_changing_file_is_not_indexed(library, monkeypatch):
    db, root = library
    file = root / "track.mp3"
    file.write_bytes(b"first")
    original = hashlib.file_digest

    def mutate(stream, name):
        result = original(stream, name)
        file.write_bytes(b"changed length")
        return result

    monkeypatch.setattr(hashlib, "file_digest", mutate)
    scan_catalog(db, root)
    assert catalog_page(db, None)["items"] == []


def test_unicode_catalog_pages_fit_limits(library):
    db, root = library
    for i in range(45):
        (root / f"{i:03d}-音楽.mp3").write_bytes(str(i).encode())
    scan_catalog(db, root)
    cursor = None
    seen = []
    while True:
        page = catalog_page(db, cursor)
        assert len(page["items"]) <= 20
        assert len(json.dumps(page, ensure_ascii=False).encode()) <= 8192
        seen.extend(x["track_id"] for x in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 45


def test_missing_source_keeps_metadata(library):
    db, root = library
    file = root / "offline.mp3"
    file.write_bytes(b"offline")
    scan_catalog(db, root)
    file.unlink()
    scan_catalog(db, root)
    tracks = catalog_page(db, None)["items"]
    assert tracks[0]["available"] is False
    assert tracks[0]["filename"] == "offline.mp3"


def test_server_startup_indexes_existing_folder(tmp_path):
    from fastapi.testclient import TestClient
    from garmin_sync.config import Settings
    from garmin_sync.admin import create_admin_app
    root = tmp_path / "music"
    root.mkdir()
    (root / "first.mp3").write_bytes(b"first")
    client = TestClient(create_admin_app(Settings(root, tmp_path / "data")), base_url="http://127.0.0.1:8000")
    assert client.get("/api/local/catalog").json()["items"][0]["filename"] == "first.mp3"
