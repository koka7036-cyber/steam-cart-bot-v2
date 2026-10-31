"""SQLite-backed idempotency and single-flight lease primitives.

This backend is suitable for local processes sharing one database file on one
machine. It is NOT a cross-run GitHub Actions lease unless the database is
hosted on a durable filesystem with SQLite locking guarantees. The workflow
must not use runner-local SQLite as a durable claim store.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import sqlite3
from pathlib import Path
from typing import Iterator
from contextlib import contextmanager

LEASE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class LeaseClaim:
    task_key: str
    owner: str
    acquired: bool
    status: str
    lease_expires_at: str | None = None


def task_key(repository: str, issue_number: int) -> str:
    if not repository or repository.count("/") != 1:
        raise ValueError("repository must be owner/name")
    if isinstance(issue_number, bool) or not isinstance(issue_number, int) or issue_number <= 0:
        raise ValueError("issue_number must be a positive integer")
    return f"{repository.lower()}#{issue_number}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class SQLiteLeaseStore:
    """Atomic single-flight store using BEGIN IMMEDIATE and a unique task key."""

    def __init__(self, database: str | Path, *, timeout_seconds: float = 10.0) -> None:
        self.database = str(database)
        self.timeout_seconds = timeout_seconds
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.database,
            timeout=self.timeout_seconds,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout = 10000")
            connection.execute("PRAGMA journal_mode = WAL")
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS dispatcher_leases (
                    task_key TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('running','completed','failed')),
                    lease_expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    last_error TEXT
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS dispatcher_runs (
                    run_id TEXT PRIMARY KEY,
                    task_key TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    summary TEXT,
                    FOREIGN KEY(task_key) REFERENCES dispatcher_leases(task_key)
                )
            """)
            db.execute("PRAGMA user_version = 1")

    def claim(
        self,
        *,
        key: str,
        owner: str,
        lease_seconds: int = 900,
    ) -> LeaseClaim:
        if not key or not owner:
            raise ValueError("key and owner are required")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or lease_seconds < 30:
            raise ValueError("lease_seconds must be an integer >= 30")

        now = _utc_now()
        expires = now + timedelta(seconds=lease_seconds)
        now_text, expires_text = _iso(now), _iso(expires)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT task_key, owner, status, lease_expires_at, attempt "
                "FROM dispatcher_leases WHERE task_key = ?",
                (key,),
            ).fetchone()

            if current is None:
                db.execute(
                    "INSERT INTO dispatcher_leases "
                    "(task_key, owner, status, lease_expires_at, created_at, updated_at, attempt) "
                    "VALUES (?, ?, 'running', ?, ?, ?, 1)",
                    (key, owner, expires_text, now_text, now_text),
                )
                db.commit()
                return LeaseClaim(key, owner, True, "acquired", expires_text)

            if current["status"] == "completed":
                db.commit()
                return LeaseClaim(key, owner, False, "already_completed", current["lease_expires_at"])

            current_expiry = current["lease_expires_at"]
            expired = not current_expiry or current_expiry <= now_text
            if current["status"] == "running" and not expired:
                db.commit()
                return LeaseClaim(key, owner, False, "already_running", current_expiry)

            # Failed tasks and expired leases can be reclaimed by a new owner.
            # Same-owner retries are also allowed after lease expiry.
            db.execute(
                "UPDATE dispatcher_leases SET owner = ?, status = 'running', "
                "lease_expires_at = ?, updated_at = ?, attempt = attempt + 1, last_error = NULL "
                "WHERE task_key = ?",
                (owner, expires_text, now_text, key),
            )
            db.commit()
            return LeaseClaim(key, owner, True, "reclaimed", expires_text)

    def renew(self, *, key: str, owner: str, lease_seconds: int = 900) -> bool:
        if lease_seconds < 30:
            raise ValueError("lease_seconds must be >= 30")
        now = _utc_now()
        expires = _iso(now + timedelta(seconds=lease_seconds))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute(
                "UPDATE dispatcher_leases SET lease_expires_at = ?, updated_at = ? "
                "WHERE task_key = ? AND owner = ? AND status = 'running' "
                "AND lease_expires_at > ?",
                (expires, _iso(now), key, owner, _iso(now)),
            )
            db.commit()
            return result.rowcount == 1

    def finish(
        self,
        *,
        key: str,
        owner: str,
        success: bool,
        error: str | None = None,
    ) -> bool:
        now = _iso(_utc_now())
        status = "completed" if success else "failed"
        safe_error = None if success else (error or "unspecified failure")[:500]
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute(
                "UPDATE dispatcher_leases SET status = ?, lease_expires_at = NULL, "
                "updated_at = ?, last_error = ? "
                "WHERE task_key = ? AND owner = ? AND status = 'running'",
                (status, now, safe_error, key, owner),
            )
            db.commit()
            return result.rowcount == 1

    def get(self, key: str) -> dict | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT task_key, owner, status, lease_expires_at, created_at, updated_at, "
                "attempt, last_error FROM dispatcher_leases WHERE task_key = ?",
                (key,),
            ).fetchone()
        return dict(row) if row else None

    def record_run(
        self,
        *,
        run_id: str,
        key: str,
        owner: str,
        status: str,
        summary: str | None = None,
    ) -> bool:
        if not run_id or not owner or status not in {"started", "completed", "failed"}:
            raise ValueError("invalid run metadata")
        now = _iso(_utc_now())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            exists = db.execute(
                "SELECT 1 FROM dispatcher_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if exists:
                db.commit()
                return False
            db.execute(
                "INSERT INTO dispatcher_runs "
                "(run_id, task_key, owner, status, started_at, finished_at, summary) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id, key, owner, status, now,
                    now if status != "started" else None,
                    (summary or "")[:1000] if summary else None,
                ),
            )
            db.commit()
            return True


def artifact_idempotency_key(repository: str, issue_number: int, task_body: str) -> str:
    """Stable opaque fingerprint for logs/metadata; do not treat as a lease."""
    base = task_key(repository, issue_number) + "\n" + (task_body or "")
    return hashlib.sha256(base.encode("utf-8")).hexdigest()
