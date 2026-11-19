"""Tiny SQLite helper: plain SQL, dict rows, auto-create + auto-seed on first use."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def db_path() -> Path:
    """Database location; override with FLUX_DB_PATH (used by tests)."""
    return Path(os.environ.get("FLUX_DB_PATH", ROOT / "data" / "flux_bunkers.db"))


def _connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connect(path: Path | None = None):
    """Context-managed connection that commits on success and always closes."""
    conn = _connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def query_one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def scalar(sql: str, params: Iterable[Any] = ()) -> Any:
    with connect() as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
        return row[0] if row else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Run a write statement; returns lastrowid."""
    with connect() as conn:
        cur = conn.execute(sql, tuple(params))
        return cur.lastrowid


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())


def init_db(force_reseed: bool = False) -> None:
    """Create the schema and seed demo data if the database is empty (or on request)."""
    from db import seed  # local import to avoid a cycle

    path = db_path()
    if force_reseed and path.exists():
        path.unlink()
    with connect(path) as conn:
        create_schema(conn)
        has_data = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        if not has_data:
            seed.seed(conn)
        else:
            migrate(conn)


def migrate(conn: sqlite3.Connection) -> None:
    """Bring an existing database up to date without touching its data.

    New tables arrive via CREATE TABLE IF NOT EXISTS in schema.sql; this fills in their seed rows
    (travel logistics) only if they are still empty.
    """
    from db.seed_travel import seed_travel

    seed_travel(conn)
