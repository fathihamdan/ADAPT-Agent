"""Real flight search via the Atlas Flight Booking CLI (`atlas-flight`), when available.

This is a best-effort data source, not a hard dependency: if the CLI isn't installed,
isn't authenticated, or a search simply fails, every function here returns an empty
result rather than raising, so callers can fall back to mock data transparently.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime

from adapt.models import DisruptionCause, Flight, FlightStatus

_SEGMENT_TIME_FMT = "%Y%m%d%H%M"


def is_available() -> bool:
    return shutil.which("atlas-flight") is not None


def _parse_segment_time(raw: str) -> datetime:
    return datetime.strptime(raw, _SEGMENT_TIME_FMT)


def _offer_to_legs(offer: dict) -> list[Flight] | None:
    legs: list[Flight] = []
    for seg in offer.get("segments", []):
        try:
            legs.append(
                Flight(
                    flight_no=seg["flight_number"],
                    airline=seg.get("carrier") or "?",
                    origin=seg["departure_airport"],
                    destination=seg["arrival_airport"],
                    sched_dep=_parse_segment_time(seg["departure_time"]),
                    sched_arr=_parse_segment_time(seg["arrival_time"]),
                    terminal_dep="-",
                    terminal_arr="-",
                    status=FlightStatus.ON_TIME,
                    cause=DisruptionCause.NONE,
                )
            )
        except (KeyError, ValueError):
            return None
    return legs or None


def search(origin: str, destination: str, depart_date: str, adults: int = 1, timeout: float = 20.0) -> list[list[Flight]]:
    """Return one leg-list per offer for the given route/date via the Atlas CLI.

    Returns [] on any failure (CLI missing, unauthenticated, timeout, bad JSON, no
    offers) - callers should treat that as "no real data available" and fall back.
    """
    if not is_available():
        return []

    try:
        result = subprocess.run(
            [
                "atlas-flight",
                "search",
                "--origin",
                origin.upper(),
                "--destination",
                destination.upper(),
                "--depart",
                depart_date,
                "--adults",
                str(adults),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    if payload.get("status") != "success":
        return []

    itineraries: list[list[Flight]] = []
    for offer in payload.get("data", {}).get("offers", []):
        legs = _offer_to_legs(offer)
        if legs:
            itineraries.append(legs)
    return itineraries
