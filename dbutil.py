import sqlite3


def connect(db_path: str, *, timeout_s: float = 30.0) -> sqlite3.Connection:
    """
    Centralized sqlite connection helper.

    - WAL + busy_timeout reduce "database is locked" errors under light concurrency.
    - foreign_keys=ON makes constraints actually enforceable.
    """
    conn = sqlite3.connect(db_path, timeout=timeout_s)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.OperationalError:
        # Some sqlite builds / file types may not support WAL (e.g. read-only).
        pass
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn

