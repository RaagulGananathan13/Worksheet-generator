"""SQLite persistence. Each write transaction acquires its lock before reading."""

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time
from uuid import uuid4


ATTEMPTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY,
    worksheet_id TEXT NOT NULL REFERENCES worksheets(id),
    student_id TEXT NOT NULL REFERENCES users(id),
    teacher_id TEXT NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    pages TEXT NOT NULL,
    questions TEXT NOT NULL,
    worksheet_revision INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
      CHECK(status IN ('draft', 'grading', 'review', 'graded')),
    version INTEGER NOT NULL DEFAULT 1,
    answers TEXT NOT NULL DEFAULT '{}',
    results TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    submitted_at TEXT,
    grading_started REAL,
    submission_mode TEXT NOT NULL DEFAULT 'online' CHECK(submission_mode IN ('online', 'paper')),
    paper TEXT NOT NULL DEFAULT '{}',
    grading_tries INTEGER NOT NULL DEFAULT 0,
    attempt_number INTEGER NOT NULL DEFAULT 1 CHECK(attempt_number >= 1),
    previous_attempt_id TEXT REFERENCES attempts(id),
    UNIQUE(student_id, worksheet_id, attempt_number),
    UNIQUE(previous_attempt_id)
);
"""


PAPER_COLUMNS = (
    ("submission_mode", "TEXT NOT NULL DEFAULT 'online' CHECK(submission_mode IN ('online', 'paper'))"),
    ("paper", "TEXT NOT NULL DEFAULT '{}'"),
    ("grading_tries", "INTEGER NOT NULL DEFAULT 0"),
)


ATTEMPT_INDEXES = (
    "CREATE INDEX IF NOT EXISTS attempts_teacher ON attempts(teacher_id, updated_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS attempts_one_active ON attempts(student_id, worksheet_id) WHERE status IN ('draft', 'grading')",
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('teacher', 'student')),
    teacher_id TEXT REFERENCES users(id),
    class_code TEXT UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
CREATE TABLE IF NOT EXISTS worksheets (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    pages TEXT NOT NULL,
    questions TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    published INTEGER NOT NULL DEFAULT 0,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_id, sha256)
);
""" + ATTEMPTS_SCHEMA + """
CREATE TABLE IF NOT EXISTS review_audit (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(id),
    teacher_id TEXT NOT NULL REFERENCES users(id),
    action TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, directory: Path):
        self.directory = Path(directory).resolve()
        self.path = self.directory / "grading.sqlite3"

    def initialize(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            # Concurrent first startups may contend while enabling WAL. SQLite's
            # busy timeout does not reliably wait for this particular PRAGMA.
            for retry in range(6):
                try:
                    connection.execute("PRAGMA journal_mode=WAL")
                    break
                except sqlite3.OperationalError as error:
                    if error.sqlite_errorcode not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED} or retry == 5:
                        raise
                    time.sleep(0.05 * (2 ** retry))
            connection.executescript(SCHEMA)
        self._migrate_attempt_history()

    def _backup_before_attempt_migration(self):
        """Copy SQLite's live snapshot, including WAL, without copying open files.

        The caller holds BEGIN IMMEDIATE but has not changed any rows. A separate
        reader can therefore make a consistent backup while competing writers
        remain locked out. The backup deliberately stays available for recovery.
        """
        backup_directory = self.directory / "backups"
        backup_directory.mkdir(exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = backup_directory / f"before-attempt-history-{timestamp}-{uuid4().hex[:8]}.sqlite3"
        with self.connection() as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("The pre-upgrade database backup could not be verified. No attempts were migrated.")
        return destination

    def _migrate_attempt_history(self):
        """Upgrade the legacy one-attempt constraint without losing any records.

        SQLite requires a table rebuild to remove the old UNIQUE constraint.
        Foreign keys are disabled only on this private migration connection;
        all existing rows and review-audit references are checked before commit.
        Failure rolls back the complete rebuild and leaves the backup intact.
        """
        with self.connection() as connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("BEGIN IMMEDIATE")
            try:
                columns = [row["name"] for row in connection.execute("PRAGMA table_info(attempts)")]
                if "attempt_number" not in columns:
                    self._backup_before_attempt_migration()
                    connection.execute(ATTEMPTS_SCHEMA.replace("IF NOT EXISTS attempts (", "attempts_retry_migration (", 1))
                    # Names come from SQLite schema metadata, never request data.
                    quoted = ",".join('"' + name.replace('"', '""') + '"' for name in columns)
                    connection.execute(f"INSERT INTO attempts_retry_migration ({quoted}) SELECT {quoted} FROM attempts")
                    connection.execute("DROP TABLE attempts")
                    connection.execute("ALTER TABLE attempts_retry_migration RENAME TO attempts")
                # Paper submissions add columns only; existing rows keep every value.
                present = {row["name"] for row in connection.execute("PRAGMA table_info(attempts)")}
                for name, definition in PAPER_COLUMNS:
                    if name not in present:
                        connection.execute(f"ALTER TABLE attempts ADD COLUMN {name} {definition}")
                for statement in ATTEMPT_INDEXES:
                    connection.execute(statement)
                if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise RuntimeError("Database relationships failed verification. The attempt-history upgrade was rolled back.")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.execute("PRAGMA foreign_keys=ON")

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self):
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def one(self, sql, parameters=()):
        with self.connection() as connection:
            row = connection.execute(sql, parameters).fetchone()
            return dict(row) if row is not None else None

    def all(self, sql, parameters=()):
        with self.connection() as connection:
            return [dict(row) for row in connection.execute(sql, parameters).fetchall()]
