"""Passengers the ops desk has already rebooked, and what they were moved onto.

A triage queue is only useful if handled work leaves it. Without this, a passenger
stays in the Connection Risk Queue at CRITICAL forever after being rerouted, and
the desk re-reads the same case every refresh with no way to tell "not yet looked
at" from "already solved".

Confirming a reroute writes a row here; the queue filters those passengers out and
the Rerouted Passengers view reads them back. Kept in SQLite next to the other
local stores so a restart doesn't resurrect solved cases.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CACHE_DIR = _PROJECT_ROOT / ".cache"
_DB_PATH = _CACHE_DIR / "rerouted.sqlite3"


def _connect() -> sqlite3.Connection:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rerouted (
            passenger_id     TEXT PRIMARY KEY,
            passenger_name   TEXT NOT NULL,
            original_risk    TEXT,
            original_risk_pct INTEGER,
            connection_airport TEXT,
            option_code      TEXT,
            option_route     TEXT,
            option_departs   TEXT,
            option_arrives   TEXT,
            delay_vs_original INTEGER,
            connections      INTEGER,
            rerouted_at      REAL NOT NULL
        )
        """
    )
    return conn


def mark_rerouted(passenger_id: str, passenger_name: str, option: dict[str, Any],
                  original_risk: str | None = None, original_risk_pct: int | None = None,
                  connection_airport: str | None = None) -> bool:
    """Record that this passenger has been moved onto `option`. Idempotent."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO rerouted (
                    passenger_id, passenger_name, original_risk, original_risk_pct,
                    connection_airport, option_code, option_route, option_departs,
                    option_arrives, delay_vs_original, connections, rerouted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    passenger_id,
                    passenger_name,
                    original_risk,
                    original_risk_pct,
                    connection_airport,
                    option.get("code"),
                    option.get("route"),
                    option.get("depart") or option.get("departs"),
                    option.get("arrival") or option.get("arrives"),
                    option.get("delay_vs_original"),
                    option.get("connections"),
                    time.time(),
                ),
            )
        return True
    except sqlite3.Error:
        return False


def is_rerouted(passenger_id: str) -> bool:
    return passenger_id in rerouted_ids()


def rerouted_ids() -> set[str]:
    """Every passenger id already rerouted - used to filter the live queue."""
    if not _DB_PATH.exists():
        return set()
    try:
        with _connect() as conn:
            return {row[0] for row in conn.execute("SELECT passenger_id FROM rerouted")}
    except sqlite3.Error:
        return set()


def list_rerouted() -> list[dict[str, Any]]:
    """Rerouted passengers, most recently handled first."""
    if not _DB_PATH.exists():
        return []
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT passenger_id, passenger_name, original_risk, original_risk_pct, "
                "connection_airport, option_code, option_route, option_departs, "
                "option_arrives, delay_vs_original, connections, rerouted_at "
                "FROM rerouted ORDER BY rerouted_at DESC"
            ).fetchall()
    except sqlite3.Error:
        return []

    return [
        {
            "passenger_id": r[0],
            "name": r[1],
            "original_risk": r[2],
            "original_risk_pct": r[3],
            "connection_airport": r[4],
            "option_code": r[5],
            "option_route": r[6],
            "option_departs": r[7],
            "option_arrives": r[8],
            "delay_vs_original": r[9],
            "connections": r[10],
            "rerouted_at": r[11],
            "rerouted_age_seconds": max(0.0, time.time() - r[11]),
        }
        for r in rows
    ]


def undo(passenger_id: str) -> bool:
    """Put a passenger back in the queue - the desk's escape hatch for a misclick."""
    try:
        with _connect() as conn:
            return (conn.execute(
                "DELETE FROM rerouted WHERE passenger_id = ?", (passenger_id,)
            ).rowcount or 0) > 0
    except sqlite3.Error:
        return False
