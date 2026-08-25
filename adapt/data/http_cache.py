"""Persistent on-disk cache for third-party API responses.

The in-process caches elsewhere in ADAPT only live as long as the process does,
so every `uvicorn` restart re-spends quota on requests whose answers we already
had. AviationStack's free tier allows roughly 100 calls a *month*, which a few
days of ordinary development burns through without ever showing a user anything
new. This module keeps those responses in a local SQLite file instead.

Three behaviours matter more than raw hit rate:

- **Survives restarts.** The whole point: a restart must not cost quota.
- **Stale-if-error.** When the upstream API fails (a 429 in particular), serving
  yesterday's flight list beats serving nothing. The caller is told the data is
  stale so it can say so rather than passing it off as live.
- **Offline mode.** `ADAPT_OFFLINE=1` never spends a call at all, answering only
  from cache. Useful for demos and for working on the UI without a live key.

SQLite is stdlib, handles concurrent readers, and keeps the cache inspectable
with any sqlite client - no extra dependency for what is fundamentally a
key/value store with timestamps.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CACHE_DIR = _PROJECT_ROOT / ".cache"
_DB_PATH = _CACHE_DIR / "api_cache.sqlite3"

# 24 hours. Flight *status* goes stale in minutes, but the expensive-to-refetch
# part here is the schedule shape, and a demo tolerates a day-old snapshot far
# better than it tolerates an exhausted quota. Override per environment.
DEFAULT_TTL_SECONDS = 86_400.0


def _ttl_seconds() -> float:
    raw = os.environ.get("ADAPT_CACHE_TTL_SECONDS")
    if not raw:
        return DEFAULT_TTL_SECONDS
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_TTL_SECONDS


def is_offline() -> bool:
    """True when ADAPT_OFFLINE is set: answer from cache, never spend a call."""
    return os.environ.get("ADAPT_OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}


def _connect() -> sqlite3.Connection:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # A fresh connection per call keeps this safe across FastAPI's threadpool and
    # the ThreadPoolExecutors in rerouting; SQLite handles the locking.
    conn = sqlite3.connect(_DB_PATH, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS responses (
            key        TEXT PRIMARY KEY,
            source     TEXT NOT NULL,
            fetched_at REAL NOT NULL,
            payload    TEXT NOT NULL
        )
        """
    )
    return conn


def get(source: str, key: str, ttl: float | None = None) -> tuple[Any, float] | None:
    """Return (payload, age_seconds) when a fresh entry exists, else None."""
    entry = get_stale(source, key)
    if entry is None:
        return None
    payload, age = entry
    limit = _ttl_seconds() if ttl is None else ttl
    return entry if age <= limit else None


def get_stale(source: str, key: str) -> tuple[Any, float] | None:
    """Return (payload, age_seconds) regardless of age - the stale-if-error path."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT payload, fetched_at FROM responses WHERE key = ? AND source = ?",
                (key, source),
            ).fetchone()
    except sqlite3.Error:
        # A corrupt or unwritable cache must never take the app down with it.
        return None
    if row is None:
        return None
    try:
        payload = json.loads(row[0])
    except json.JSONDecodeError:
        return None
    return payload, max(0.0, time.time() - row[1])


def put(source: str, key: str, payload: Any) -> None:
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO responses (key, source, fetched_at, payload) "
                "VALUES (?, ?, ?, ?)",
                (key, source, time.time(), json.dumps(payload)),
            )
    except (sqlite3.Error, TypeError, ValueError):
        # Caching is an optimisation; failing to store must not fail the request.
        pass


def stats() -> dict[str, Any]:
    """Cache contents by source, for `adapt cache-status`."""
    if not _DB_PATH.exists():
        return {"path": str(_DB_PATH), "exists": False, "entries": 0, "sources": {}, "size_bytes": 0}
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT source, COUNT(*), MIN(fetched_at), MAX(fetched_at) "
                "FROM responses GROUP BY source"
            ).fetchall()
    except sqlite3.Error:
        rows = []

    now = time.time()
    sources = {
        source: {
            "entries": count,
            "oldest_age_seconds": now - oldest,
            "newest_age_seconds": now - newest,
        }
        for source, count, oldest, newest in rows
    }
    return {
        "path": str(_DB_PATH),
        "exists": True,
        "entries": sum(s["entries"] for s in sources.values()),
        "sources": sources,
        "size_bytes": _DB_PATH.stat().st_size,
        "ttl_seconds": _ttl_seconds(),
        "offline": is_offline(),
    }


def clear(source: str | None = None) -> int:
    """Delete cached entries (all, or just one source). Returns rows removed."""
    if not _DB_PATH.exists():
        return 0
    try:
        with _connect() as conn:
            cursor = (
                conn.execute("DELETE FROM responses WHERE source = ?", (source,))
                if source
                else conn.execute("DELETE FROM responses")
            )
            return cursor.rowcount or 0
    except sqlite3.Error:
        return 0
