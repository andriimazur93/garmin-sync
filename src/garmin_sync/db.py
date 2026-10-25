"""Transactional SQLite persistence, shared by the two local listeners."""
from contextlib import contextmanager
from pathlib import Path
import secrets
import sqlite3
import uuid
import time


class Database:
    def __init__(self, path: Path, clock=time.time):
        self.clock = clock
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Create with private permissions before writing any credentials.
        path.touch(mode=0o600, exist_ok=True)
        path.chmod(0o600)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            for key, value in {
                "schema_version": "3", "desired_revision": "0", "server_id": str(uuid.uuid4()),
                "device_token": secrets.token_urlsafe(32), "csrf_token": secrets.token_urlsafe(32),
            }.items():
                conn.execute("INSERT OR IGNORE INTO metadata VALUES (?, ?)", (key, value))

            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tracks (
                    track_id TEXT PRIMARY KEY, filename TEXT NOT NULL, size_bytes INTEGER NOT NULL,
                    available INTEGER NOT NULL, relative_path TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS desired (
                    track_id TEXT PRIMARY KEY REFERENCES tracks(track_id), present INTEGER NOT NULL,
                    revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS association (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), device_epoch TEXT NOT NULL,
                    server_id TEXT NOT NULL, confirmed INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sync_sessions (
                    session_id TEXT PRIMARY KEY, device_epoch TEXT NOT NULL, server_id TEXT NOT NULL,
                    protocol_version INTEGER NOT NULL, expires_at REAL NOT NULL,
                    desired_revision INTEGER, before_inventory TEXT, after_inventory TEXT,
                    plan TEXT, outcome TEXT, plan_confirmed INTEGER);
                CREATE TABLE IF NOT EXISTS operation_results (
                    session_id TEXT REFERENCES sync_sessions(session_id), operation_id TEXT,
                    result TEXT NOT NULL, PRIMARY KEY(session_id,operation_id));
                CREATE TABLE IF NOT EXISTS inventory_generations (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, generation_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL REFERENCES sync_sessions(session_id), report TEXT);
                CREATE TABLE IF NOT EXISTS inventory_pages (
                    generation_id TEXT NOT NULL REFERENCES inventory_generations(generation_id) ON DELETE CASCADE,
                    page_number INTEGER NOT NULL, entries TEXT NOT NULL,
                    PRIMARY KEY(generation_id,page_number));
                CREATE TABLE IF NOT EXISTS latest_inventory (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), generation_seq INTEGER NOT NULL,
                    report TEXT NOT NULL, entries TEXT NOT NULL);
                UPDATE metadata SET value='3'  WHERE key='schema_version';
            """)

            columns = {r[1] for r in conn.execute('PRAGMA table_info(sync_sessions)')}
            if 'plan_confirmed' not in columns:
                conn.execute('ALTER TABLE sync_sessions ADD COLUMN plan_confirmed INTEGER')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def identity(self) -> dict[str, str]:
        with self.connect() as conn:
            return dict(conn.execute("SELECT key,value FROM metadata").fetchall())
