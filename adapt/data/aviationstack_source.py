"""Real flight status via the AviationStack API, when an API key is configured.

Best-effort, like adapt/data/atlas_source.py: if the key is missing, the API errors,
or the flight isn't found, lookup_flight() returns None rather than raising - callers
decide what "no live data" means for them.

AviationStack's free tier is HTTP-only (no HTTPS) and doesn't report *why* a flight
is disrupted - just that it is. We map that honestly onto DisruptionCause.UNKNOWN
rather than guessing a cause we don't have.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from adapt.data import http_cache
from adapt.models import DisruptionCause, Flight, FlightStatus

_API_URL = "http://api.aviationstack.com/v1/flights"

_STATUS_MAP = {
    "cancelled": FlightStatus.CANCELLED,
    "diverted": FlightStatus.DIVERTED,
}

# AviationStack's free tier caps out around 100 requests/*month*, and get_passengers()
# can call into this module several times in a single page load (queue list + a
# selected passenger's detail). A short cache keeps rapid successive calls - and repeat
# testing - from burning quota on requests that would return the same thing anyway.
_CACHE_TTL_SECONDS = 60.0
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

# Why the most recent request produced no data. Every failure here is best-effort
# (callers get None and fall back to mock), but "no live data" and "your API quota
# ran out three weeks ago" are very different problems for whoever is watching the
# table, and silently returning mock rows hides the difference.
_last_error: str | None = None

# Age of the data the last successful lookup returned. 0.0 means a live call;
# anything larger came from the on-disk cache, and callers that display the data
# should say so rather than presenting day-old rows as current.
_last_age_seconds: float = 0.0

# Namespace for this API's entries in the shared on-disk cache.
_CACHE_SOURCE = "aviationstack"


def last_error() -> str | None:
    """Human-readable reason the last lookup returned nothing, or None if it worked."""
    return _last_error


def last_age_seconds() -> float:
    """How old the data from the last successful lookup was. 0.0 = fetched live."""
    return _last_age_seconds


def _format_age(seconds: float) -> str:
    if seconds < 90:
        return f"{int(seconds)}s"
    if seconds < 5400:
        return f"{int(seconds / 60)}min"
    if seconds < 172_800:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86_400:.1f}d"


def _serve_stale(cache_key: str, reason: str) -> list[dict[str, Any]] | None:
    """Fall back to cached data of any age when the live call fails.

    A 429 three weeks into the month is the normal case here: yesterday's flight
    list is far more useful than an empty table, provided the caller is told the
    data is stale so it never gets presented as live.
    """
    global _last_error, _last_age_seconds

    stale = http_cache.get_stale(_CACHE_SOURCE, cache_key)
    if stale is None:
        _last_error = reason
        return None

    results, age = stale
    _last_error = f"{reason} - serving cached data {_format_age(age)} old"
    _last_age_seconds = age
    return results


def is_available() -> bool:
    return bool(os.environ.get("AVIATIONSTACK_API_KEY"))


def _error_message(raw_body: str) -> str | None:
    """Pull AviationStack's `error.message` (or `error.code`) out of an error body."""
    try:
        error = json.loads(raw_body)["error"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    if isinstance(error, str):
        return error
    return error.get("message") or error.get("code")


def _parse_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        # Drop tzinfo rather than convert to UTC - ADAPT treats sched_dep/sched_arr
        # as local wall-clock time at each airport throughout (mock data and Atlas
        # results are naive too), so keep the same convention here.
        return datetime.fromisoformat(raw).replace(tzinfo=None)
    except ValueError:
        return None


def _flight_from_result(result: dict[str, Any]) -> Flight | None:
    departure = result.get("departure") or {}
    arrival = result.get("arrival") or {}
    flight_info = result.get("flight") or {}
    airline_info = result.get("airline") or {}

    flight_no = flight_info.get("iata") or flight_info.get("icao")
    origin = departure.get("iata")
    destination = arrival.get("iata")
    sched_dep = _parse_time(departure.get("scheduled"))
    sched_arr = _parse_time(arrival.get("scheduled"))
    if not (flight_no and origin and destination and sched_dep and sched_arr):
        return None

    raw_status = (result.get("flight_status") or "").lower()
    delay_minutes = departure.get("delay") or arrival.get("delay") or 0

    if raw_status in _STATUS_MAP:
        status = _STATUS_MAP[raw_status]
    elif delay_minutes and delay_minutes > 0:
        status = FlightStatus.DELAYED
    else:
        status = FlightStatus.ON_TIME

    cause = DisruptionCause.NONE if status == FlightStatus.ON_TIME else DisruptionCause.UNKNOWN

    raw_ops_note = (
        f"AVIATIONSTACK LIVE STATUS: {raw_status.upper() or 'UNKNOWN'} - "
        f"departure delay {delay_minutes}min - source does not report a cause"
    )

    return Flight(
        flight_no=flight_no,
        airline=airline_info.get("name") or flight_no,
        origin=origin,
        destination=destination,
        sched_dep=sched_dep,
        sched_arr=sched_arr,
        terminal_dep=departure.get("terminal") or "-",
        terminal_arr=arrival.get("terminal") or "-",
        status=status,
        delay_minutes=int(delay_minutes) if status == FlightStatus.DELAYED else 0,
        cause=cause,
        raw_ops_note=raw_ops_note,
        gate=departure.get("gate") or "",
    )


def _request(extra_params: dict[str, str], timeout: float) -> list[dict[str, Any]] | None:
    global _last_error, _last_age_seconds

    api_key = os.environ.get("AVIATIONSTACK_API_KEY")
    if not api_key:
        _last_error = "AVIATIONSTACK_API_KEY is not set"
        return None

    # The key deliberately excludes the API key: rotating a spent key must not
    # throw away everything the old one already paid for.
    cache_key = json.dumps(extra_params, sort_keys=True)

    cached = _cache.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    # L2: on-disk, survives restarts. This is the layer that actually saves quota.
    stored = http_cache.get(_CACHE_SOURCE, cache_key)
    if stored is not None:
        results, age = stored
        _last_error = None
        _cache[cache_key] = (time.monotonic(), results)
        _last_age_seconds = age
        return results

    if http_cache.is_offline():
        # Offline mode: answer from cache at any age, but never spend a call.
        stale = http_cache.get_stale(_CACHE_SOURCE, cache_key)
        if stale is not None:
            results, age = stale
            _last_error = f"offline mode - cached data {_format_age(age)} old"
            _last_age_seconds = age
            return results
        _last_error = "offline mode (ADAPT_OFFLINE) and nothing cached for this request"
        return None

    query = urllib.parse.urlencode({"access_key": api_key, **extra_params})
    url = f"{_API_URL}?{query}"

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # The interesting failures arrive as HTTP errors with a JSON body - most
        # often 429 usage_limit_reached, which is a billing problem rather than a
        # "no flights found" one. Read the body so the caller can say which.
        reason = _error_message(exc.read().decode("utf-8", errors="replace")) or f"HTTP {exc.code}"
        return _serve_stale(cache_key, reason)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return _serve_stale(cache_key, f"could not reach AviationStack ({exc})")

    if "error" in payload:
        reason = _error_message(json.dumps(payload)) or "AviationStack returned an error"
        return _serve_stale(cache_key, reason)

    results = payload.get("data") or []
    if not results:
        _last_error = "AviationStack returned no matching flights"
        return None

    http_cache.put(_CACHE_SOURCE, cache_key, results)

    _last_error = None
    _last_age_seconds = 0.0
    _cache[cache_key] = (time.monotonic(), results)
    return results


def lookup_flight(flight_iata: str, timeout: float = 15.0) -> Flight | None:
    results = _request({"flight_iata": flight_iata.upper()}, timeout)
    if not results:
        return None
    return _flight_from_result(results[0])


def list_live_flights(limit: int = 25, timeout: float = 15.0) -> list[Flight]:
    """Real flights AviationStack is currently tracking worldwide - no route/flight
    filter, just whatever's actually in the air (or scheduled) right now.
    """
    results = _request({"limit": str(limit)}, timeout)
    if not results:
        return []
    flights = [_flight_from_result(r) for r in results]
    return [f for f in flights if f is not None]


# AviationStack's free plan refuses limit > 100 outright (403
# function_access_restricted), so a large dataset can only be built by paging.
MAX_PAGE_SIZE = 100


def harvest(
    pages: int = 5,
    page_size: int = MAX_PAGE_SIZE,
    timeout: float = 30.0,
    on_page: Any = None,
) -> dict[str, Any]:
    """Page through the live flight feed and store every flight locally.

    Each page costs one API call and yields up to 100 flights, so the caller is
    trading a known slice of a ~100-call monthly quota for a permanent local
    dataset. Stops early on the first failed or empty page rather than burning
    the remaining budget on requests that are already failing.

    Returns a summary dict: pages fetched, API calls spent, flights stored.
    """
    from adapt.data import flight_store

    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    api_calls = 0
    stored = 0
    added = 0
    updated = 0
    seen: set[tuple[str, datetime]] = set()
    error: str | None = None

    for page in range(pages):
        offset = page * page_size
        results = _request({"limit": str(page_size), "offset": str(offset)}, timeout)
        api_calls += 1
        if not results:
            error = last_error()
            break

        flights = [f for f in (_flight_from_result(r) for r in results) if f is not None]
        # The feed shifts under pagination (it is a live view, not a stable
        # snapshot), so the same flight can surface on two pages. Dedupe within a
        # run; the (flight_no, sched_dep) primary key handles it across runs.
        fresh = [f for f in flights if (f.flight_no, f.sched_dep) not in seen]
        seen.update((f.flight_no, f.sched_dep) for f in fresh)

        page_added, page_updated = flight_store.save_detailed(fresh)
        added += page_added
        updated += page_updated
        stored += page_added + page_updated
        if on_page:
            on_page(page + 1, len(fresh), stored)

        if len(results) < page_size:
            break  # Last page - no point spending another call on an empty one.

    return {
        "pages": min(pages, api_calls),
        "api_calls": api_calls,
        "stored": stored,
        "added": added,
        "updated": updated,
        "total_in_db": flight_store.count(),
        "error": error,
    }


def find_disrupted_flight(arr_iata: str | None = None, timeout: float = 15.0) -> Flight | None:
    """A real, currently-disrupted flight - cancelled flights first (a clean
    unambiguous signal), then any active flight with a positive departure delay
    (there's no "delayed" flight_status value on this API; delay is a separate field).

    arr_iata optionally constrains the search to flights landing at a specific
    airport, so the result can slot into an itinerary's existing connecting leg
    without breaking geographic continuity.
    """
    base_params = {"arr_iata": arr_iata} if arr_iata else {}

    cancelled = _request({**base_params, "flight_status": "cancelled", "limit": "5"}, timeout)
    if cancelled:
        flight = _flight_from_result(cancelled[0])
        if flight:
            return flight

    active = _request({**base_params, "flight_status": "active", "limit": "20"}, timeout)
    for result in active or []:
        departure = result.get("departure") or {}
        delay = departure.get("delay") or 0
        if delay and delay > 0:
            flight = _flight_from_result(result)
            if flight:
                return flight

    return None


def find_diverted_flight(timeout: float = 15.0) -> Flight | None:
    """A real, currently-diverted flight. Kept separate from find_disrupted_flight()
    rather than folded into it - diversions are rare, and callers that specifically
    want to demonstrate DIVERTED status shouldn't silently get a cancelled/delayed
    flight instead just because one was easier to find.
    """
    results = _request({"flight_status": "diverted", "limit": "5"}, timeout)
    if not results:
        return None
    return _flight_from_result(results[0])
