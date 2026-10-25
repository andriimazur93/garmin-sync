"""Content-addressed catalog with safe filesystem access and stable pages."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import uuid
from .db import Database


class CatalogError(ValueError):
    pass


def _schema(db):
    with db.connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS tracks (
            track_id TEXT PRIMARY KEY, filename TEXT NOT NULL, size_bytes INTEGER NOT NULL,
            available INTEGER NOT NULL, relative_path TEXT NOT NULL)""")
        c.execute("CREATE TABLE IF NOT EXISTS catalog_snapshots (id TEXT PRIMARY KEY, created REAL, items TEXT)")


def _open_beneath(root: Path, relative: str):
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or any(x in {".", ".."} for x in parts):
        raise CatalogError("Invalid catalog path")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise CatalogError("Source is not a regular file")
        return os.fdopen(fd, "rb")
    finally:
        os.close(directory)


def scan_catalog(db: Database, root: Path) -> dict:
    _schema(db)
    root = root.resolve()
    found = {}
    skipped = 0
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() != ".mp3":
                continue
            try:
                relative = str(path.relative_to(root))
                with _open_beneath(root, relative) as stream:
                    before = os.fstat(stream.fileno())
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    after = os.fstat(stream.fileno())
                    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise CatalogError("Source changed during scan")
                found.setdefault(digest, (digest, path.name, before.st_size, 1, relative))
            except (OSError, ValueError):
                skipped += 1
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        c.execute("INSERT OR REPLACE INTO metadata VALUES ('music_root', ?)", (str(root),))
        c.execute("UPDATE tracks SET available=0")
        c.executemany("""INSERT INTO tracks VALUES (?,?,?,?,?) ON CONFLICT(track_id) DO UPDATE SET
            filename=excluded.filename,size_bytes=excluded.size_bytes,
            available=excluded.available,relative_path=excluded.relative_path""", found.values())
    return {"indexed": len(found), "skipped": skipped, "missing_root": not root.is_dir()}


def catalog_page(db: Database, cursor: str | None) -> dict:
    _schema(db)
    with db.connect() as c:
        c.execute("DELETE FROM catalog_snapshots WHERE created < ?", (time.time() - 300,))
        if cursor:
            try:
                snapshot_id, index_text = cursor.split(":")
                index = int(index_text)
                row = c.execute("SELECT items FROM catalog_snapshots WHERE id=?", (snapshot_id,)).fetchone()
                if row is None or index < 0:
                    raise ValueError()
                items = json.loads(row[0])
                if index >= len(items):
                    raise ValueError()
            except (ValueError, TypeError):
                raise CatalogError("Catalog cursor expired or invalid; refresh the catalog") from None
        else:
            snapshot_id, index = uuid.uuid4().hex, 0
            items = [{**dict(row), "available": bool(row["available"])} for row in c.execute(
                "SELECT track_id,filename,size_bytes,available FROM tracks ORDER BY filename,track_id")]
            c.execute("INSERT INTO catalog_snapshots VALUES (?,?,?)", (snapshot_id, time.time(), json.dumps(items)))
    count = min(20, len(items) - index)
    while True:
        end = index + count
        page = {"items": items[index:end], "next_cursor": f"{snapshot_id}:{end}" if end < len(items) else None}
        if len(json.dumps(page, ensure_ascii=False).encode()) <= 8192:
            return page
        count -= 1
        if count <= 0:
            raise CatalogError("A catalog record exceeds the watch response budget")


def resolve_track(db: Database, track_id: str):
    """Return a private immutable snapshot; callers must close it."""
    _schema(db)
    with db.connect() as c:
        row = c.execute("SELECT * FROM tracks WHERE track_id=? AND available=1", (track_id,)).fetchone()
        root = c.execute("SELECT value FROM metadata WHERE key='music_root'").fetchone()
    if row is None or root is None:
        raise CatalogError("Track is unavailable; rescan the music directory")
    snapshot = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)
    digest = hashlib.sha256()
    try:
        with _open_beneath(Path(root[0]), row["relative_path"]) as source:
            while chunk := source.read(65536):
                snapshot.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != track_id or snapshot.tell() != row["size_bytes"]:
            raise CatalogError("Track changed; rescan before downloading")
        snapshot.seek(0)
        return snapshot
    except (OSError, ValueError) as exc:
        snapshot.close()
        raise CatalogError(str(exc)) from exc
