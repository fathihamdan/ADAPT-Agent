"""Rerouting Recommender: finds and ranks alternative flights when a disruption (a
cancelled leg or a high-risk connection) threatens an itinerary.

Two data sources are supported, in this priority order:

1. **Atlas** (optional) — live inventory via the `atlas-flight` CLI. Offers may be
   nonstop or multi-segment (Atlas sells real connecting itineraries such as
   `6E1038 + 6E1485` via BLR); every segment is preserved as its own leg so the
   transit gaps stay visible. Offers carry real offer IDs, fares and ancillary
   availability. Falls back automatically on any failure (CLI missing,
   unauthorized, rate-limited, empty result set, network error).

   When Atlas has **no through-fare at all** for a city pair (KUL -> AMS is one:
   Atlas sells KUL -> DXB and DXB -> AMS but nothing end-to-end), ADAPT builds
   the connection itself by searching plausible hubs and pairing legs. Those
   options are marked `self_transfer` because they are two separate tickets -
   the ops desk must see that a misconnect carries no airline protection.

2. **Mock** (default) — the in-repo flight schedule. Still used as the source
   for one-stop connection options even when Atlas supplies direct flights.

The caller picks the source by passing `use_atlas=True`; any Atlas failure is
swallowed into a `fallback_reason` string and surfaced through the narrative so
the user sees *why* they got mock results.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any

from adapt.data.airports import hubs_for
from adapt.data.mock_data import get_flight_db
from adapt.llm.base import LLMClient
from adapt.models import Flight, FlightStatus, RerouteOption

MIN_CONNECTION_BUFFER_MINUTES = 45

# How many Atlas offers to keep as ranking candidates before the final shortlist.
# Deliberately larger than the caller's `max_options`: truncating early used to
# drop connecting itineraries before they could compete with nonstops.
MAX_ATLAS_CANDIDATES = 12

# Self-transfer bounds. The floor is far above MIN_CONNECTION_BUFFER_MINUTES
# because separate tickets mean re-checking bags and clearing immigration with no
# airline holding the flight; the ceiling stops us proposing an overnight sit as
# if it were a connection.
SELF_TRANSFER_MIN_MINUTES = 120
SELF_TRANSFER_MAX_MINUTES = 600

# Each hub costs live CLI searches, so the candidate list stays short.
MAX_HUB_CANDIDATES = 4
MAX_LEGS_PER_HUB = 3


def _legs_summary(legs: list[Flight]) -> str:
    return " + ".join(f.flight_no for f in legs)


def layover_gaps(legs: list[Flight]) -> list[int]:
    """Transit gap in minutes at each intermediate stop; empty for a nonstop.

    Shared with the web layer so the ops desk and the agent narrative always
    quote the same numbers.
    """
    return [
        round((legs[i + 1].sched_dep - legs[i].sched_arr).total_seconds() / 60)
        for i in range(len(legs) - 1)
    ]


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
    """Convert an `AtlasOffer` into an ADAPT `RerouteOption`, one leg per segment.

    Atlas sells genuine multi-segment itineraries, so flattening an offer into a
    single synthetic flight would report a connecting trip as if it were nonstop
    and hide the transit gap entirely. Every segment is kept as its own leg and
    the layovers are derived from the leg times.
    """
    segments = sorted(offer.segments, key=lambda s: s.departure)
    legs = [
        Flight(
            flight_no=s.flight_number,
            airline=s.carrier,
            origin=s.origin,
            destination=s.destination,
            sched_dep=s.departure,
            sched_arr=s.arrival,
            status=FlightStatus.ON_TIME,
            source="atlas",
        )
        for s in segments
    ]
    if not legs:
        # Offer-level fallback: the client normally drops segment-less offers, so
        # this only guards against an unexpected payload shape.
        legs = [
            Flight(
                flight_no=offer.flight_number,
                airline=offer.carrier,
                origin=offer.origin,
                destination=offer.destination,
                sched_dep=offer.departure,
                sched_arr=offer.arrival,
                status=FlightStatus.ON_TIME,
                source="atlas",
            )
        ]

    connections = len(legs) - 1
    if connections:
        via = " -> ".join(leg.destination for leg in legs[:-1])
        notes = f"via {via}"
    else:
        notes = "live inventory via Atlas"

    new_arrival = legs[-1].sched_arr
    delay_vs_original = round((new_arrival - original_arrival).total_seconds() / 60)
    return RerouteOption(
        replacement_legs=legs,
        new_arrival=new_arrival,
        delay_vs_original_minutes=delay_vs_original,
        connections=connections,
        notes=notes,
        atlas_offer_id=offer.offer_id,
        atlas_search_id=offer.search_id,
        atlas_price=offer.total_price,
        atlas_currency=offer.currency,
        atlas_price_status=offer.price_status,
        atlas_bookable=offer.bookable,
        atlas_ancillary_supported=list(offer.ancillary_supported),
    )


def _has_usable_times(offer) -> bool:
    """Reject offers whose timestamps failed to parse (the client yields
    `datetime.min`) or run backwards - layover math on those is meaningless.
    """
    stamps = [(s.departure, s.arrival) for s in offer.segments] or [
        (offer.departure, offer.arrival)
    ]
    return all(
        dep != datetime.min and arr != datetime.min and arr >= dep for dep, arr in stamps
    )


def _find_atlas_options(
    origin: str,
    destination: str,
    not_before: datetime,
    original_arrival: datetime,
    atlas_env: str,
    client: Any,
) -> tuple[list[RerouteOption], str | None]:
    """Query Atlas for nonstop and connecting through-fares, returning
    (options, fallback_reason).

    `fallback_reason` is non-None when Atlas could not be used; the caller
    should fall back to mock data and surface the reason in the narrative.
    """
    from adapt.atlas import AtlasError, AtlasUnavailable

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
        return [], f"Atlas has no through-fare for {origin} -> {destination}"

    # Filter to departures at or after `not_before` (the CLI accepts a date,
    # not a time, so we still enforce the time gate locally) and drop offers we
    # cannot time-reason about.
    filtered = [o for o in offers if o.departure >= not_before and _has_usable_times(o)]
    if not filtered:
        return [], "Atlas offers all depart before the required time"

    options = [_atlas_offer_to_option(o, original_arrival) for o in filtered]
    options.sort(key=lambda o: (o.new_arrival, o.connections, o.atlas_price or 0.0))
    return options[:MAX_ATLAS_CANDIDATES], f"live Atlas results{_env_note(atlas_env)}"


def _atlas_client() -> tuple[Any | None, str | None]:
    """Return (client, fallback_reason). Exactly one of the two is set.

    Constructing a client costs a version check and an auth check, so the caller
    builds one and shares it across every search in the request.
    """
    try:
        from adapt.atlas import AtlasClient, AtlasUnavailable
    except Exception as exc:  # pragma: no cover - import failure path
        return None, f"Atlas client could not be imported ({exc})"

    try:
        client = AtlasClient()
    except AtlasUnavailable as exc:
        return None, f"Atlas CLI unavailable ({exc}); using local schedule"

    if not client.is_authorized():
        return None, "Atlas not authorized; using local schedule (run `atlas-flight auth login`)"
    return client, None


def _env_note(atlas_env: str) -> str:
    return "" if atlas_env == "production" else f" (Sandbox — {atlas_env})"


def _stitch(
    first, second, transfer_at: str, original_arrival: datetime
) -> RerouteOption:
    """Join two independent Atlas offers into one self-transfer itinerary."""
    legs: list[Flight] = []
    for offer in (first, second):
        for segment in sorted(offer.segments, key=lambda s: s.departure):
            legs.append(
                Flight(
                    flight_no=segment.flight_number,
                    airline=segment.carrier,
                    origin=segment.origin,
                    destination=segment.destination,
                    sched_dep=segment.departure,
                    sched_arr=segment.arrival,
                    status=FlightStatus.ON_TIME,
                    source="atlas",
                )
            )

    # Only sum fares when both tickets are priced in the same currency; a bogus
    # total is worse than none at all.
    same_currency = first.currency == second.currency
    new_arrival = legs[-1].sched_arr
    return RerouteOption(
        replacement_legs=legs,
        new_arrival=new_arrival,
        delay_vs_original_minutes=round(
            (new_arrival - original_arrival).total_seconds() / 60
        ),
        connections=len(legs) - 1,
        notes=f"2 separate tickets, self-transfer in {transfer_at}",
        atlas_offer_id=first.offer_id,
        atlas_offer_ids=[first.offer_id, second.offer_id],
        atlas_search_id=first.search_id,
        atlas_price=(first.total_price + second.total_price) if same_currency else None,
        atlas_currency=first.currency if same_currency else None,
        # A ticket is only as firm as its weaker half.
        atlas_price_status=(
            "current"
            if first.price_status == "current" and second.price_status == "current"
            else "reference"
        ),
        atlas_bookable=bool(first.bookable and second.bookable),
        atlas_ancillary_supported=sorted(
            set(first.ancillary_supported) & set(second.ancillary_supported)
        ),
        self_transfer=True,
        # The handover sits at the end of the first ticket, which may itself have
        # carried the passenger through one or more protected stops.
        self_transfer_after_leg=max(len(first.segments) - 1, 0),
    )


def _find_atlas_self_transfer(
    origin: str,
    destination: str,
    not_before: datetime,
    original_arrival: datetime,
    atlas_env: str,
    client: Any,
) -> tuple[list[RerouteOption], str | None]:
    """Build connecting itineraries by hand when Atlas sells no through-fare.

    Runs in two parallel phases (origin -> hub, then hub -> destination) because
    the second phase's dates depend on when the first legs actually land. Returns
    (options, note); an empty list means no hub produced a valid pairing.
    """
    from adapt.atlas import AtlasError, AtlasUnavailable

    hubs = hubs_for(origin, destination, limit=MAX_HUB_CANDIDATES)
    if not hubs:
        return [], None

    def search(route: tuple[str, str, datetime]) -> list:
        leg_origin, leg_destination, depart = route
        try:
            return client.search(
                origin=leg_origin, destination=leg_destination, depart=depart, adults=1
            )
        except (AtlasError, AtlasUnavailable):
            # One dead hub must not sink the whole search.
            return []

    with ThreadPoolExecutor(max_workers=len(hubs)) as pool:
        first_results = list(pool.map(search, [(origin, hub, not_before) for hub in hubs]))

    # Group by where each offer *actually* lands: Atlas may substitute a nearby
    # metro airport, and the onward leg has to depart from the real arrival point.
    inbound: dict[str, list] = {}
    for offers in first_results:
        for offer in offers:
            if offer.departure < not_before or not _has_usable_times(offer):
                continue
            if offer.destination in (origin, destination):
                continue
            inbound.setdefault(offer.destination, []).append(offer)

    onward_routes: set[tuple[str, str, datetime]] = set()
    for transfer_at, offers in inbound.items():
        offers.sort(key=lambda o: o.arrival)
        del offers[MAX_LEGS_PER_HUB:]
        for offer in offers:
            earliest = offer.arrival + timedelta(minutes=SELF_TRANSFER_MIN_MINUTES)
            latest = offer.arrival + timedelta(minutes=SELF_TRANSFER_MAX_MINUTES)
            # A viable onward flight can fall on either side of midnight, and the
            # CLI searches one date at a time.
            for day_offset in range((latest.date() - earliest.date()).days + 1):
                onward_routes.add(
                    (
                        transfer_at,
                        destination,
                        datetime.combine(
                            earliest.date() + timedelta(days=day_offset), datetime.min.time()
                        ),
                    )
                )

    if not onward_routes:
        return [], None

    ordered_routes = sorted(onward_routes, key=lambda r: (r[0], r[2]))
    with ThreadPoolExecutor(max_workers=len(ordered_routes)) as pool:
        onward_results = list(pool.map(search, ordered_routes))

    outbound: dict[str, list] = {}
    for (transfer_at, _, _), offers in zip(ordered_routes, onward_results):
        for offer in offers:
            if _has_usable_times(offer):
                outbound.setdefault(transfer_at, []).append(offer)

    options: list[RerouteOption] = []
    for transfer_at, first_offers in inbound.items():
        for first in first_offers:
            for second in outbound.get(transfer_at, []):
                gap = round((second.departure - first.arrival).total_seconds() / 60)
                if not SELF_TRANSFER_MIN_MINUTES <= gap <= SELF_TRANSFER_MAX_MINUTES:
                    continue
                options.append(_stitch(first, second, transfer_at, original_arrival))

    if not options:
        return [], None

    options.sort(key=lambda o: (o.new_arrival, o.connections, o.atlas_price or 0.0))
    return (
        options[:MAX_ATLAS_CANDIDATES],
        f"no through-fare for {origin} -> {destination}; "
        f"built self-transfer routings via Atlas{_env_note(atlas_env)}",
    )


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
        client, unavailable_reason = _atlas_client()
        if client is None:
            atlas_note = unavailable_reason
        else:
            atlas_options, reason = _find_atlas_options(
                origin, destination, not_before, original_arrival, atlas_env, client
            )
            atlas_note = reason
            options.extend(atlas_options)

            # Atlas sells no end-to-end ticket for this pair, so assemble the
            # connection ourselves rather than reporting "no routes found" while
            # bookable legs sit one hub away.
            if not atlas_options:
                stitched, stitched_reason = _find_atlas_self_transfer(
                    origin, destination, not_before, original_arrival, atlas_env, client
                )
                if stitched:
                    options.extend(stitched)
                    atlas_note = stitched_reason

    mock_options = _find_mock_options(origin, destination, not_before, original_arrival, exclude_flight_no)

    # De-dupe on the whole itinerary, not just its first leg: `6E1038` nonstop and
    # `6E1038 + 6E1485` via BLR share a first flight but are different products,
    # and keying on the first leg alone used to discard the connecting one.
    seen: set[tuple[tuple[str, datetime], ...]] = set()
    merged: list[RerouteOption] = []
    for opt in options + mock_options:
        if not opt.replacement_legs:
            continue
        key = tuple((leg.flight_no, leg.sched_dep) for leg in opt.replacement_legs)
        if key in seen:
            continue
        seen.add(key)
        merged.append(opt)

    # Earliest arrival wins, then fewer stops, then cheaper. Connecting
    # itineraries compete on the same terms as nonstops rather than being
    # excluded - a one-stop that lands first is genuinely the better option.
    # Single-ticket options outrank self-transfers at equal arrival: the same
    # journey is worth less when a misconnect is the passenger's own problem.
    merged.sort(
        key=lambda o: (o.new_arrival, o.self_transfer, o.connections, o.atlas_price or 0.0)
    )
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
                # Two separate tickets - the narrative must not present this as a
                # protected connection.
                "self_transfer": opt.self_transfer,
                # Transit gaps so the narrative can flag a tight connection
                # instead of silently recommending one.
                "layovers": [
                    f"{gap} min in {opt.replacement_legs[i].destination}"
                    for i, gap in enumerate(layover_gaps(opt.replacement_legs))
                ],
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
