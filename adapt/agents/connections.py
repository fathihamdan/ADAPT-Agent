"""Connection detection: which of a passenger's booked flights actually connect.

A passenger's flight list is flat and can span different airlines (self-connect
tickets sold by a 3rd-party dealer) - nothing in the data pre-declares which
flights form a connection the way a single-airline itinerary's leg order used to.
This is the piece that figures that out, so connection_risk.assess() can keep
doing exactly the math it already does, just fed real detected pairs.
"""

from __future__ import annotations

from adapt.models import Flight


def find_connections(flights: list[Flight]) -> list[tuple[Flight, Flight]]:
    """Sort a passenger's flights chronologically, then return the adjacent pairs
    that actually connect: same airport (A's destination is B's origin) and B
    departs no earlier than A was scheduled to land. Flights that don't chain -
    unrelated bookings, a gap, wrong airport - simply aren't returned as a pair.
    """
    ordered = sorted(flights, key=lambda f: f.sched_dep)
    pairs: list[tuple[Flight, Flight]] = []
    for a, b in zip(ordered, ordered[1:]):
        if a.destination == b.origin and b.sched_dep >= a.sched_arr:
            pairs.append((a, b))
    return pairs
