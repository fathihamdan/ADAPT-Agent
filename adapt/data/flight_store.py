"""Local flight database: real flights harvested from AviationStack, kept for good.

This is deliberately *not* the same thing as `http_cache`. That module caches raw
API responses so a restart doesn't re-buy them, and its contents are disposable -
`adapt cache-clear` wipes it without a second thought. This module is the opposite:
an accumulating dataset that cost real API quota to build, queryable long after the
responses that produced it have expired.

The distinction matters because of how AviationStack's free tier is shaped: 100
rows per request, ~100 requests a month. Harvesting ten pages spends a tenth of the
month's quota and yields a thousand real flights - worth keeping permanently, and
worth never deleting by accident. `adapt cache-clear` leaves this file alone.

Rows are keyed on (flight_no, sched_dep) so re-harvesting updates a flight's status
in place rather than duplicating it, and the table grows across harvest runs.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from adapt.models import DisruptionCause, Flight, FlightStatus

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CACHE_DIR = _PROJECT_ROOT / ".cache"
_DB_PATH = _CACHE_DIR / "flights.sqlite3"

_COLUMNS = (
    "flight_no", "airline", "origin", "destination", "sched_dep", "sched_arr",
    "terminal_dep", "terminal_arr", "status", "delay_minutes", "cause",
    "raw_ops_note", "gate", "harvested_at",
)


def _connect() -> sqlite3.Connection:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS flights (
            flight_no     TEXT NOT NULL,
            airline       TEXT NOT NULL,
            origin        TEXT NOT NULL,
            destination   TEXT NOT NULL,
            sched_dep     TEXT NOT NULL,
            sched_arr     TEXT NOT NULL,
            terminal_dep  TEXT,
            terminal_arr  TEXT,
            status        TEXT,
            delay_minutes INTEGER,
            cause         TEXT,
            raw_ops_note  TEXT,
            gate          TEXT,
            harvested_at  REAL NOT NULL,
            PRIMARY KEY (flight_no, sched_dep)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flights_route ON flights (origin, destination)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flights_dep ON flights (sched_dep)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flights_status ON flights (status)")
    return conn


def save_detailed(flights: list[Flight]) -> tuple[int, int]:
    """Store flights, returning (added, updated).

    The (flight_no, sched_dep) primary key is what guarantees no duplicates: the
    same flight re-harvested overwrites its own row rather than creating a second
    one. Existing rows are still refreshed rather than skipped, because a flight
    that has since gone from ON_TIME to CANCELLED is the single most valuable
    thing a reload can tell an ops desk - but that is an update, not a duplicate.
    """
    if not flights:
        return 0, 0
    keys = {(f.flight_no, f.sched_dep.isoformat()) for f in flights}
    existing = _existing_keys(keys)
    added = len(keys - existing)
    written = save(flights)
    if not written:
        return 0, 0
    return added, len(keys) - added


def _existing_keys(keys: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """Which (flight_no, sched_dep) pairs are already stored."""
    if not keys or not _DB_PATH.exists():
        return set()
    found: set[tuple[str, str]] = set()
    key_list = list(keys)
    try:
        with _connect() as conn:
            # Chunked to stay well under SQLite's parameter limit on big harvests.
            for start in range(0, len(key_list), 400):
                chunk = key_list[start : start + 400]
                placeholders = ", ".join("(?, ?)" * 1 for _ in chunk)
                params = [value for pair in chunk for value in pair]
                rows = conn.execute(
                    f"SELECT flight_no, sched_dep FROM flights "
                    f"WHERE (flight_no, sched_dep) IN ({placeholders})",
                    params,
                ).fetchall()
                found.update((r[0], r[1]) for r in rows)
    except sqlite3.Error:
        return set()
    return found


def save(flights: list[Flight]) -> int:
    """Insert or update flights. Returns how many rows were written."""
    if not flights:
        return 0
    now = time.time()
    rows = [
        (
            f.flight_no, f.airline, f.origin, f.destination,
            f.sched_dep.isoformat(), f.sched_arr.isoformat(),
            f.terminal_dep, f.terminal_arr, f.status.value, f.delay_minutes,
            f.cause.value, f.raw_ops_note, f.gate, now,
        )
        for f in flights
    ]
    placeholders = ", ".join("?" * len(_COLUMNS))
    try:
        with _connect() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO flights ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                rows,
            )
        return len(rows)
    except sqlite3.Error:
        return 0


def _row_to_flight(row: tuple) -> Flight | None:
    try:
        return Flight(
            flight_no=row[0],
            airline=row[1],
            origin=row[2],
            destination=row[3],
            sched_dep=datetime.fromisoformat(row[4]),
            sched_arr=datetime.fromisoformat(row[5]),
            terminal_dep=row[6] or "",
            terminal_arr=row[7] or "",
            status=FlightStatus(row[8]),
            delay_minutes=row[9] or 0,
            cause=DisruptionCause(row[10]),
            raw_ops_note=row[11] or "",
            gate=row[12] or "",
            source="aviationstack",
        )
    except (ValueError, TypeError):
        # One unparseable row must not sink the whole query.
        return None


def load(
    limit: int = 100,
    origin: str | None = None,
    destination: str | None = None,
    status: str | None = None,
    disrupted_only: bool = False,
) -> list[Flight]:
    """Read harvested flights back, newest departure first. Zero API calls."""
    where: list[str] = []
    params: list[Any] = []
    if origin:
        where.append("origin = ?")
        params.append(origin.upper())
    if destination:
        where.append("destination = ?")
        params.append(destination.upper())
    if status:
        where.append("status = ?")
        params.append(status.upper())
    if disrupted_only:
        where.append("status != 'ON_TIME'")

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    query = (
        f"SELECT {', '.join(_COLUMNS[:-1])} FROM flights {clause} "
        f"ORDER BY sched_dep DESC LIMIT ?"
    )
    params.append(limit)

    try:
        with _connect() as conn:
            rows = conn.execute(query, params).fetchall()
    except sqlite3.Error:
        return []

    flights = [_row_to_flight(r) for r in rows]
    return [f for f in flights if f is not None]


def count() -> int:
    if not _DB_PATH.exists():
        return 0
    try:
        with _connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
    except sqlite3.Error:
        return 0


def stats() -> dict[str, Any]:
    """Summary for `adapt db-status`: size, coverage and how stale the data is."""
    if not _DB_PATH.exists():
        return {"path": str(_DB_PATH), "exists": False, "flights": 0}
    try:
        with _connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
            routes = conn.execute(
                "SELECT COUNT(DISTINCT origin || destination) FROM flights"
            ).fetchone()[0]
            airports = conn.execute(
                "SELECT COUNT(*) FROM (SELECT origin AS a FROM flights UNION SELECT destination FROM flights)"
            ).fetchone()[0]
            disrupted = conn.execute(
                "SELECT COUNT(*) FROM flights WHERE status != 'ON_TIME'"
            ).fetchone()[0]
            newest = conn.execute("SELECT MAX(harvested_at) FROM flights").fetchone()[0]
            by_status = dict(
                conn.execute("SELECT status, COUNT(*) FROM flights GROUP BY status").fetchall()
            )
    except sqlite3.Error:
        return {"path": str(_DB_PATH), "exists": True, "flights": 0}

    return {
        "path": str(_DB_PATH),
        "exists": True,
        "flights": total,
        "routes": routes,
        "airports": airports,
        "disrupted": disrupted,
        "by_status": by_status,
        "size_bytes": _DB_PATH.stat().st_size,
        "harvested_age_seconds": (time.time() - newest) if newest else None,
    }


def clear() -> int:
    """Drop every harvested flight. Separate from cache-clear on purpose - this
    data cost API quota, so deleting it is always an explicit decision."""
    if not _DB_PATH.exists():
        return 0
    try:
        with _connect() as conn:
            return conn.execute("DELETE FROM flights").rowcount or 0
    except sqlite3.Error:
        return 0
