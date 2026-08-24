"""Rerouting Recommender: finds and ranks alternative flights when a disruption (a
cancelled leg or a high-risk connection) threatens an itinerary.

Two data sources are supported, in this priority order:

1. **Atlas** (optional) — live inventory via the `atlas-flight` CLI. Produces
   direct-flight `RerouteOption`s carrying real offer IDs, fares and ancillary
   availability. Falls back automatically on any failure (CLI missing,
   unauthorized, rate-limited, empty result set, network error).

2. **Mock** (default) — the in-repo flight schedule. Still used as the source
   for one-stop connection options even when Atlas supplies direct flights.

The caller picks the source by passing `use_atlas=True`; any Atlas failure is
swallowed into a `fallback_reason` string and surfaced through the narrative so
the user sees *why* they got mock results.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from adapt.data.mock_data import get_flight_db
from adapt.llm.base import LLMClient
from adapt.models import Flight, FlightStatus, RerouteOption

MIN_CONNECTION_BUFFER_MINUTES = 45


def _legs_summary(legs: list[Flight]) -> str:
    return " + ".join(f.flight_no for f in legs)


# ---------------------------------------------------------------------------
# Mock-data path (unchanged behaviour, just extracted for reuse)
# ---------------------------------------------------------------------------


def _find_mock_options(
    origin: str,
    destination: str,
    not_before: datetime,
    original_arrival: datetime,
    exclude_flight_no: str | None,
) -> list[RerouteOption]:
    db = [f for f in get_flight_db() if f.status.value != "CANCELLED"]
    if exclude_flight_no:
        db = [f for f in db if f.flight_no != exclude_flight_no]

    options: list[RerouteOption] = []

    # Direct flights.
    for f in db:
        if f.origin == origin and f.destination == destination and f.sched_dep >= not_before:
            delay_vs_original = round((f.sched_arr - original_arrival).total_seconds() / 60)
            options.append(
                RerouteOption(
                    replacement_legs=[f],
                    new_arrival=f.sched_arr,
                    delay_vs_original_minutes=delay_vs_original,
                    connections=0,
                )
            )

    # One-stop options via any intermediate airport.
    first_legs = [f for f in db if f.origin == origin and f.sched_dep >= not_before]
    for leg1 in first_legs:
        earliest_next_dep = leg1.sched_arr + timedelta(minutes=MIN_CONNECTION_BUFFER_MINUTES)
        second_legs = [
            f
            for f in db
            if f.origin == leg1.destination
            and f.destination == destination
            and f.sched_dep >= earliest_next_dep
        ]
        for leg2 in second_legs:
            delay_vs_original = round((leg2.sched_arr - original_arrival).total_seconds() / 60)
            options.append(
                RerouteOption(
                    replacement_legs=[leg1, leg2],
                    new_arrival=leg2.sched_arr,
                    delay_vs_original_minutes=delay_vs_original,
                    connections=1,
                    notes=f"via {leg1.destination}",
                )
            )
    return options


# ---------------------------------------------------------------------------
# Atlas path
# ---------------------------------------------------------------------------


def _atlas_offer_to_option(offer, original_arrival: datetime) -> RerouteOption:
    """Convert an `AtlasOffer` into an ADAPT `RerouteOption`."""
    flight = Flight(
        flight_no=offer.flight_number,
        airline=offer.carrier,
        origin=offer.origin,
        destination=offer.destination,
        sched_dep=offer.departure,
        sched_arr=offer.arrival,
        status=FlightStatus.ON_TIME,
        source="atlas",
    )
    delay_vs_original = round((offer.arrival - original_arrival).total_seconds() / 60)
    return RerouteOption(
        replacement_legs=[flight],
        new_arrival=offer.arrival,
        delay_vs_original_minutes=delay_vs_original,
        connections=0,
        notes="live inventory via Atlas",
        atlas_offer_id=offer.offer_id,
        atlas_search_id=offer.search_id,
        atlas_price=offer.total_price,
        atlas_currency=offer.currency,
        atlas_price_status=offer.price_status,
        atlas_bookable=offer.bookable,
        atlas_ancillary_supported=list(offer.ancillary_supported),
    )


def _find_atlas_options(
    origin: str,
    destination: str,
    not_before: datetime,
    original_arrival: datetime,
    atlas_env: str,
) -> tuple[list[RerouteOption], str | None]:
    """Query Atlas for direct flights, returning (options, fallback_reason).

    `fallback_reason` is non-None when Atlas could not be used; the caller
    should fall back to mock data and surface the reason in the narrative.
    """
    try:
        from adapt.atlas import AtlasClient, AtlasError, AtlasUnavailable
    except Exception as exc:  # pragma: no cover - import failure path
        return [], f"Atlas client could not be imported ({exc})"

    try:
        client = AtlasClient()
    except AtlasUnavailable as exc:
        return [], f"Atlas CLI unavailable ({exc}); using local schedule"

    if not client.is_authorized():
        return [], "Atlas not authorized; using local schedule (run `atlas-flight auth login`)"

    try:
        offers = client.search(
            origin=origin,
            destination=destination,
            depart=not_before,
            adults=1,
        )
    except AtlasError as exc:
        return [], f"Atlas returned {exc.code}; using local schedule"
    except AtlasUnavailable as exc:
        return [], f"Atlas unreachable ({exc}); using local schedule"

    if not offers:
        return [], "Atlas returned no offers; using local schedule"

    # Filter to departures at or after `not_before` (the CLI accepts a date,
    # not a time, so we still enforce the time gate locally).
    filtered = [o for o in offers if o.departure >= not_before]
    if not filtered:
        return [], "Atlas offers all depart before the required time; using local schedule"

    options = [_atlas_offer_to_option(o, original_arrival) for o in filtered]
    options.sort(key=lambda o: (o.new_arrival, o.atlas_price or 0.0))
    env_note = "" if atlas_env == "production" else f" (Sandbox — {atlas_env})"
    return options[:3], f"live Atlas results{env_note}"


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def find_options(
    origin: str,
    destination: str,
    not_before: datetime,
    original_arrival: datetime,
    exclude_flight_no: str | None = None,
    max_options: int = 3,
    use_atlas: bool = False,
    atlas_env: str = "production",
) -> tuple[list[RerouteOption], str | None]:
    """Return (ranked_options, atlas_note).

    `atlas_note` is None when mock data was used without any Atlas attempt, or
    a human-readable string explaining how Atlas contributed ("live Atlas
    results", "Atlas not authorized; using local schedule", etc.).
    """
    atlas_note: str | None = None
    options: list[RerouteOption] = []

    if use_atlas:
        atlas_options, reason = _find_atlas_options(
            origin, destination, not_before, original_arrival, atlas_env
        )
        if atlas_options:
            options.extend(atlas_options)
            atlas_note = reason
        else:
            atlas_note = reason  # fall through to mock

    mock_options = _find_mock_options(origin, destination, not_before, original_arrival, exclude_flight_no)

    # De-dupe by flight number + departure time so an Atlas direct flight and a
    # mock direct flight for the same leg don't both appear.
    seen: set[tuple[str, datetime]] = set()
    merged: list[RerouteOption] = []
    for opt in options + mock_options:
        if not opt.replacement_legs:
            continue
        key = (opt.replacement_legs[0].flight_no, opt.replacement_legs[0].sched_dep)
        if key in seen:
            continue
        seen.add(key)
        merged.append(opt)

    merged.sort(key=lambda o: (o.new_arrival, o.connections))
    return merged[:max_options], atlas_note


def recommend(
    origin: str,
    destination: str,
    not_before: datetime,
    original_arrival: datetime,
    reason: str,
    llm: LLMClient,
    exclude_flight_no: str | None = None,
    max_options: int = 3,
    use_atlas: bool = False,
    atlas_env: str = "production",
) -> tuple[list[RerouteOption], str]:
    options, atlas_note = find_options(
        origin,
        destination,
        not_before,
        original_arrival,
        exclude_flight_no=exclude_flight_no,
        max_options=max_options,
        use_atlas=use_atlas,
        atlas_env=atlas_env,
    )

    # No point spending an LLM call narrating an empty result set - return a
    # deterministic message the CLI and the web API can both show as-is.
    if not options:
        note = f" ({atlas_note})" if atlas_note else ""
        return [], (
            f"No {origin} -> {destination} flights found departing after "
            f"{not_before.strftime('%a %H:%M')}{note}."
        )

    context: dict[str, Any] = {
        "destination": destination,
        "reason": reason,
        "atlas_note": atlas_note,
        "options": [
            {
                "legs_summary": _legs_summary(opt.replacement_legs)
                + (f" ({opt.notes})" if opt.notes else ""),
                "arrival": opt.new_arrival.strftime("%a %H:%M"),
                "delay_vs_original": opt.delay_vs_original_minutes,
                "connections": opt.connections,
                "from_atlas": opt.from_atlas,
                "price": (
                    f"{opt.atlas_price:.2f} {opt.atlas_currency}"
                    if opt.atlas_price is not None
                    else None
                ),
                "price_status": opt.atlas_price_status,
                "bookable": opt.atlas_bookable,
            }
            for opt in options
        ],
    }
    narrative = llm.recommend_reroute(context)
    return options, narrative
