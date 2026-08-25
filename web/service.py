"""Builds the JSON payload the GateWatch UI consumes, from real ADAPT agent output.

One function, one job: turn orchestrator.run() output into the shape the frontend
expects. No fabricated data - any UI element with no real backing data (there is
no persistence layer / flight history yet) is left out here and stays static on
the frontend instead of being wired to a fake number.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from adapt.agents import connection_risk, disruption_explainer, orchestrator, rerouting
from adapt.agents.connection_risk import DEPLANE_BUFFER_MINUTES
from adapt.agents.connections import find_connections
from adapt.data import atlas_source, aviationstack_source, flight_store
from adapt.data.airports import WORLD_AIRPORTS, airport_city, is_valid_iata
from adapt.data.mock_data import find_passenger, get_airport, get_flight_db, get_passengers, refresh_passengers
from adapt.llm import get_llm_client
from adapt.models import Flight, Passenger, RerouteOption, RiskLevel


def list_airports() -> list[dict[str, Any]]:
    """Airport picker data for the passenger-search form (code + city + name).

    Serves the curated worldwide registry - Atlas live inventory covers
    effectively every commercial airport, and the UI accepts any typed 3-letter
    code on top of this list.
    """
    return [
        {"code": a.code, "name": a.name, "city": a.city}
        for a in sorted(WORLD_AIRPORTS.values(), key=lambda a: a.city)
    ]


def _route_option_dict(
    option: RerouteOption, recommended: bool, requested_destination: str
) -> dict[str, Any]:
    """One ranked route option for the passenger-search result, with a per-leg
    breakdown so the UI can show exactly what it's proposing (not just a joined
    flight-number string).

    Every transit gap is attached to the leg it follows, so a two-stop itinerary
    reports both layovers instead of only the first one.
    """
    legs = option.replacement_legs
    first, last = legs[0], legs[-1]
    duration_minutes = round((option.new_arrival - first.sched_dep).total_seconds() / 60)
    gaps = rerouting.layover_gaps(legs)
    handover = option.self_transfer_after_leg
    return {
        "code": " + ".join(leg.flight_no for leg in legs),
        "route": option.notes or f"{first.origin} \u2192 {last.destination}",
        "departs": first.sched_dep.strftime("%a %H:%M"),
        "arrives": option.new_arrival.strftime("%a %H:%M"),
        "duration_minutes": duration_minutes,
        # Total time spent on the ground between flights (None for a nonstop).
        "layover_minutes": sum(gaps) if gaps else None,
        "layover_airports": [leg.destination for leg in legs[:-1]],
        # A gap under the connection buffer is a real operational risk for the
        # desk to see, so it is flagged rather than left for the reader to work out.
        "tight_connection": any(gap < rerouting.MIN_CONNECTION_BUFFER_MINUTES for gap in gaps),
        "connections": option.connections,
        # Atlas sometimes answers with a nearby metro airport (an ORD -> LAX search
        # can return an itinerary terminating at ONT). Surfaced explicitly so the
        # desk never books the wrong airport by accident.
        "arrives_at": last.destination,
        "destination_mismatch": last.destination != requested_destination,
        "airlines": ", ".join(dict.fromkeys(leg.airline for leg in legs)),
        "legs": [
            {
                "flight_no": leg.flight_no,
                "airline": leg.airline,
                "origin": leg.origin,
                "destination": leg.destination,
                "departs": leg.sched_dep.strftime("%a %H:%M"),
                "arrives": leg.sched_arr.strftime("%a %H:%M"),
                "layover_after_minutes": gaps[index] if index < len(gaps) else None,
                "layover_tight": (
                    gaps[index] < rerouting.MIN_CONNECTION_BUFFER_MINUTES
                    if index < len(gaps)
                    else False
                ),
                # True for the one gap where the passenger leaves the protection
                # of their first ticket - the only stop where a delay strands them.
                "self_transfer_after": handover is not None and index == handover,
            }
            for index, leg in enumerate(legs)
        ],
        "recommended": recommended,
        "source": "Atlas live inventory" if option.from_atlas else "mock schedule",
        "price": option.atlas_price,
        "currency": option.atlas_currency,
        # Stitched from two independent Atlas offers because no through-fare
        # exists. The desk must see this before quoting: a misconnect is the
        # passenger's own cost, and ticketing it means one order per offer.
        "self_transfer": option.self_transfer,
        "ticket_count": len(option.atlas_offer_ids) or 1,
        "transfer_airport": (
            legs[handover].destination if handover is not None and handover < len(legs) else None
        ),
    }


def search_passenger_routes(
    passenger_name: str,
    origin: str,
    destination: str,
    departure: datetime,
) -> dict[str, Any]:
    """Find and rank the best three routes for a new passenger booking search.

    Raises ValueError for input problems the caller can fix (same airport twice,
    or an airport outside the schedule database when no live source is
    configured) - main.py maps those to a 400 so the UI shows the message as-is.
    """
    origin = origin.strip().upper()
    destination = destination.strip().upper()

    if origin == destination:
        raise ValueError("Origin and destination must be different airports.")

    # The frontend sends ISO-8601 with a UTC offset (Date.toISOString()), which
    # Pydantic parses as timezone-aware - but mock flight times are naive local,
    # and comparing naive with aware datetimes raises TypeError. Normalize to
    # naive local time before any schedule comparison happens.
    if departure.tzinfo is not None:
        departure = departure.astimezone().replace(tzinfo=None)

    # Format-level validation only: Atlas live inventory covers effectively
    # every commercial airport, so any valid IATA code is searchable even when
    # it is not in the offline demo set. When Atlas is unavailable, codes the
    # mock schedule doesn't know simply return an empty result with an
    # explanatory note instead of an error.
    if not is_valid_iata(origin) or not is_valid_iata(destination):
        raise ValueError("Airport codes must be 3-letter IATA codes (e.g. KUL, NRT, LHR).")

    use_atlas = atlas_source.is_available()

    name = passenger_name.strip() or "the passenger"
    llm = get_llm_client()
    options, narrative = rerouting.recommend(
        origin=origin,
        destination=destination,
        not_before=departure,
        original_arrival=departure,
        reason=f"you need to book a new flight for {name}",
        llm=llm,
        max_options=3,
        use_atlas=use_atlas,
    )

    return {
        "passenger_name": name,
        "origin": origin,
        "destination": destination,
        "departure": departure.isoformat(),
        "narrative": narrative,
        "narrative_html": _markdown_bold_to_html(narrative),
        "options": [
            _route_option_dict(option, recommended=index == 0, requested_destination=destination)
            for index, option in enumerate(options)
        ],
    }

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _markdown_bold_to_html(text: str) -> str:
    escaped = _escape(text)
    bolded = _BOLD_RE.sub(r"<b>\1</b>", escaped)
    return bolded.replace("\n", "<br>")


def _flight_dict(f: Flight, source: str) -> dict[str, Any]:
    return {
        "flight_no": f.flight_no,
        "airline": f.airline,
        "origin": f.origin,
        "destination": f.destination,
        "sched_dep": f.sched_dep.strftime("%a %H:%M"),
        "sched_arr": f.sched_arr.strftime("%a %H:%M"),
        "terminal_dep": f.terminal_dep,
        "terminal_arr": f.terminal_arr,
        "status": f.status.value,
        "delay_minutes": f.delay_minutes,
        "cause": f.cause.value,
        "gate": f.gate,
        "source": source,
    }


def list_flights(
    limit: int = 200,
    origin: str | None = None,
    destination: str | None = None,
    disrupted: bool = False,
) -> list[dict[str, Any]]:
    """Real flights, preferring the locally harvested database.

    Order is local DB -> live API -> mock schedule. The local DB wins because it
    costs no quota and is usually much larger than a single 100-row live page;
    `adapt harvest` is what fills it. Falls through to the live API only when
    nothing has been harvested yet.

    The filters apply to the local DB only - the live and mock paths have no
    equivalent server-side filtering, and silently ignoring a filter would be
    worse than not offering one.
    """
    harvested = flight_store.load(
        limit=limit, origin=origin, destination=destination, disrupted_only=disrupted
    )
    if harvested:
        age = flight_store.stats().get("harvested_age_seconds") or 0.0
        return [
            _flight_dict(f, f"local flight DB (harvested {age / 3600:.1f}h ago)")
            for f in harvested
        ]

    if aviationstack_source.is_available():
        live = aviationstack_source.list_live_flights(limit=limit)
        if live:
            # Cached rows must never be labelled "live" - an ops desk acting on a
            # day-old delay is worse off than one that knows the feed is stale.
            age = aviationstack_source.last_age_seconds()
            source = (
                "AviationStack (live)"
                if age < 60
                else f"AviationStack (cached, {age / 60:.0f}min old)"
            )
            return [_flight_dict(f, source) for f in live]
        # Carry the reason into the source label rather than handing back mock rows
        # that look indistinguishable from a working live feed.
        reason = aviationstack_source.last_error() or "no live data"
        return [_flight_dict(f, f"mock schedule - live unavailable: {reason}") for f in get_flight_db()]

    return [_flight_dict(f, "mock schedule - AVIATIONSTACK_API_KEY not set") for f in get_flight_db()]


def _queue_row(passenger: Passenger) -> dict[str, Any] | None:
    """One queue row for a passenger with a detected connection - cheap: risk
    math only (connection_risk.assess() never calls the LLM), no narrative
    generation, so listing/sorting the whole queue costs nothing per passenger.
    Passengers with no detected connection return None (point 1: nothing to
    watch, nothing to show).
    """
    pairs = find_connections(passenger.flights)
    if not pairs:
        return None

    inbound, outbound = pairs[0]

    if inbound.status.value == "CANCELLED":
        risk_level, risk_pct = "CRITICAL", 100
    else:
        airport = get_airport(inbound.destination)
        if airport is None:
            return None
        risk = connection_risk.assess(passenger.passenger_id, inbound, outbound, airport, get_llm_client())
        risk_level, risk_pct = risk.risk_level.value, round(risk.probability_missed * 100)

    return {
        "passenger_id": passenger.passenger_id,
        "name": passenger.name,
        "flight_a": {"flight_no": inbound.flight_no, "airline": inbound.airline, "route": f"{inbound.origin} → {inbound.destination}", "status": inbound.status.value},
        "flight_b": {"flight_no": outbound.flight_no, "airline": outbound.airline, "route": f"{outbound.origin} → {outbound.destination}", "status": outbound.status.value},
        "connection_airport": inbound.destination,
        "risk_level": risk_level,
        "risk_pct": risk_pct,
    }


def _passenger_queue(passengers: dict[str, Passenger]) -> list[dict[str, Any]]:
    rows = [_queue_row(p) for p in passengers.values()]
    queue = [r for r in rows if r is not None]
    queue.sort(key=lambda r: -r["risk_pct"])
    return queue


def list_passenger_queue() -> list[dict[str, Any]]:
    return _passenger_queue(get_passengers())


def refresh_queue() -> list[dict[str, Any]]:
    """Manual refresh path - forces fresh live AviationStack lookups instead of
    reusing the cached-after-first-build passenger data.
    """
    return _passenger_queue(refresh_passengers())


def _city(code: str) -> str:
    airport = get_airport(code)
    return airport.city if airport else airport_city(code)


def _disruption_dict(flight: Flight, explanation: str) -> dict[str, Any]:
    return {
        "flight_no": flight.flight_no,
        "origin": flight.origin,
        "origin_city": _city(flight.origin),
        "destination": flight.destination,
        "destination_city": _city(flight.destination),
        "status": flight.status.value,
        "cause": flight.cause.value,
        "delay_minutes": flight.delay_minutes,
        "raw_feed": flight.raw_ops_note or f"{flight.status.value} — no ops note on file",
        "ai_html": _markdown_bold_to_html(explanation),
    }


def build_passenger_detail(passenger_id: str) -> dict[str, Any] | None:
    passenger = find_passenger(passenger_id)
    if passenger is None:
        return None

    llm = get_llm_client()
    report = orchestrator.run(passenger, llm)

    disruption = None
    if report.leg_explanations:
        flight, explanation = report.leg_explanations[0]
        disruption = _disruption_dict(flight, explanation)

    connection = None
    if report.connection_risks:
        risk, narrative = report.connection_risks[0]
        pct = round(risk.probability_missed * 100)
        connection = {
            "from": risk.inbound.destination,
            "to": risk.outbound.destination,
            "risk_pct": pct,
            "risk_level": risk.risk_level.value,
            "risk_band_class": {
                RiskLevel.LOW: "low",
                RiskLevel.MEDIUM: "mod",
                RiskLevel.HIGH: "high",
                RiskLevel.CRITICAL: "high",
            }[risk.risk_level],
            "available_min": round(risk.available_minutes),
            "required_min": round(risk.required_minutes),
            "buffer_min": round(risk.available_minutes - risk.required_minutes),
            "next_gate": risk.outbound.gate or "TBD",
            "ai_text": narrative,
            "factors": risk.factors,
            "steps": [
                ["Land", risk.inbound.actual_arr.strftime("%H:%M"), "on"],
                ["Deplane", (risk.inbound.actual_arr + timedelta(minutes=DEPLANE_BUFFER_MINUTES)).strftime("%H:%M"), "on"],
                ["Gate", (risk.inbound.actual_arr + timedelta(minutes=risk.required_minutes)).strftime("%H:%M"), "warn" if risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "on"],
                ["Cutoff", risk.outbound.sched_dep.strftime("%H:%M"), "warn" if risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "on"],
            ],
        }

    reroute = None
    if report.reroutes:
        bundle = report.reroutes[0]
        options = []
        for i, opt in enumerate(bundle.options):
            options.append(
                {
                    "code": " + ".join(flight.flight_no for flight in opt.replacement_legs),
                    "route": opt.notes or f"{opt.replacement_legs[0].origin} → {opt.replacement_legs[-1].destination}",
                    "depart": opt.replacement_legs[0].sched_dep.strftime("%H:%M"),
                    "arrival": opt.new_arrival.strftime("%a %H:%M"),
                    "delay_vs_original": opt.delay_vs_original_minutes,
                    "connections": opt.connections,
                    "recommended": i == 0,
                }
            )
        reroute = {
            "reason": bundle.reason,
            "narrative": bundle.narrative,
            "options": options,
        }

    return {
        "passenger_id": passenger.passenger_id,
        "name": passenger.name,
        "flights": [
            {
                "flight_no": flight.flight_no,
                "airline": flight.airline,
                "origin": flight.origin,
                "destination": flight.destination,
                "sched_dep": flight.sched_dep.strftime("%a %H:%M"),
                "sched_arr": flight.sched_arr.strftime("%a %H:%M"),
                "status": flight.status.value,
                "delay_minutes": flight.delay_minutes,
            }
            for flight in sorted(passenger.flights, key=lambda f: f.sched_dep)
        ],
        "disruption": disruption,
        "connection": connection,
        "reroute": reroute,
    }


def build_live_track(flight_iata: str) -> dict[str, Any] | None:
    """Same response shape as build_passenger_detail(), for a single real flight
    looked up live via AviationStack instead of one of the mock passengers.

    connection/reroute are always null here - a standalone flight lookup has no
    second booked flight to detect a connection or search a reroute against.
    """
    flight = aviationstack_source.lookup_flight(flight_iata)
    if flight is None:
        return None

    llm = get_llm_client()
    explanation = disruption_explainer.explain(flight, llm)

    return {
        "passenger_id": f"LIVE:{flight.flight_no}",
        "name": "Live flight lookup",
        "flights": [
            {
                "flight_no": flight.flight_no,
                "airline": flight.airline,
                "origin": flight.origin,
                "destination": flight.destination,
                "sched_dep": flight.sched_dep.strftime("%a %H:%M"),
                "sched_arr": flight.sched_arr.strftime("%a %H:%M"),
                "status": flight.status.value,
                "delay_minutes": flight.delay_minutes,
            }
        ],
        "disruption": _disruption_dict(flight, explanation),
        "connection": None,
        "reroute": None,
    }


def get_system_status() -> dict[str, Any]:
    """What's actually configured right now - the same facts `adapt status` prints
    on the CLI, exposed so the UI can show it instead of the user having to guess
    whether a given response is real or a mock fallback.
    """
    llm = get_llm_client()
    llm_is_live = "offline" not in llm.name

    return {
        "llm": {"name": llm.name, "is_live": llm_is_live},
        "rerouting": {
            "source": "Atlas Flight Booking CLI (live search)" if atlas_source.is_available() else "mock schedule only",
            "is_live": atlas_source.is_available(),
        },
        "live_tracking": {
            "source": "AviationStack" if aviationstack_source.is_available() else "not configured",
            "is_live": aviationstack_source.is_available(),
        },
    }
