"""Rerouting Recommender: finds and ranks alternative flights when a disruption (a
cancelled leg or a high-risk connection) threatens an itinerary.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from adapt.data import atlas_source
from adapt.data.mock_data import get_flight_db
from adapt.llm.base import LLMClient
from adapt.models import Flight, RerouteOption

MIN_CONNECTION_BUFFER_MINUTES = 45


def _legs_summary(legs: list[Flight]) -> str:
    return " + ".join(f.flight_no for f in legs)


def _find_options_via_atlas(
    origin: str,
    destination: str,
    not_before: datetime,
    original_arrival: datetime,
    max_options: int,
) -> list[RerouteOption]:
    offers = atlas_source.search(origin, destination, not_before.strftime("%Y-%m-%d"))

    options: list[RerouteOption] = []
    for legs in offers:
        if legs[0].sched_dep < not_before:
            continue
        new_arrival = legs[-1].sched_arr
        delay_vs_original = round((new_arrival - original_arrival).total_seconds() / 60)
        options.append(
            RerouteOption(
                replacement_legs=legs,
                new_arrival=new_arrival,
                delay_vs_original_minutes=delay_vs_original,
                connections=len(legs) - 1,
                notes="live Atlas search",
            )
        )

    options.sort(key=lambda o: (o.new_arrival, o.connections))
    return options[:max_options]


def find_options(
    origin: str,
    destination: str,
    not_before: datetime,
    original_arrival: datetime,
    exclude_flight_no: str | None = None,
    max_options: int = 3,
) -> list[RerouteOption]:
    atlas_options = _find_options_via_atlas(origin, destination, not_before, original_arrival, max_options)
    if atlas_options:
        return atlas_options

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

    options.sort(key=lambda o: (o.new_arrival, o.connections))
    return options[:max_options]


def recommend(
    origin: str,
    destination: str,
    not_before: datetime,
    original_arrival: datetime,
    reason: str,
    llm: LLMClient,
    exclude_flight_no: str | None = None,
) -> tuple[list[RerouteOption], str]:
    options = find_options(origin, destination, not_before, original_arrival, exclude_flight_no)

    context = {
        "destination": destination,
        "reason": reason,
        "options": [
            {
                "legs_summary": _legs_summary(opt.replacement_legs) + (f" ({opt.notes})" if opt.notes else ""),
                "arrival": opt.new_arrival.strftime("%a %H:%M"),
                "delay_vs_original": opt.delay_vs_original_minutes,
                "connections": opt.connections,
            }
            for opt in options
        ],
    }
    narrative = llm.recommend_reroute(context)
    return options, narrative
