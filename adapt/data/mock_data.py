"""Mock/sample data: airports, a flight database, and sample passenger itineraries.

Stands in for a real flight-data provider (FlightAware, AviationStack, an airline's own
ops feed, etc). Swap `get_flight_db()` / `get_itineraries()` for real API calls later —
nothing else in the codebase depends on this module being static.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from adapt.models import (
    Airport,
    DisruptionCause,
    Flight,
    FlightStatus,
    Itinerary,
)

# Anchor "today" to the real current date so schedules stay relevant.
TODAY = datetime.now().replace(hour=6, minute=0, second=0, microsecond=0)


def _t(hour: int, minute: int = 0, day_offset: int = 0) -> datetime:
    return TODAY.replace(hour=0, minute=0) + timedelta(days=day_offset, hours=hour, minutes=minute)


AIRPORTS: dict[str, Airport] = {
    "JFK": Airport("JFK", "John F. Kennedy Intl", "New York", mct_same_terminal=45, mct_diff_terminal=90, inter_terminal_walk_minutes=35),
    "ORD": Airport("ORD", "O'Hare Intl", "Chicago", mct_same_terminal=30, mct_diff_terminal=60, inter_terminal_walk_minutes=25),
    "DFW": Airport("DFW", "Dallas/Fort Worth Intl", "Dallas", mct_same_terminal=30, mct_diff_terminal=55, inter_terminal_walk_minutes=20),
    "ATL": Airport("ATL", "Hartsfield-Jackson Atlanta Intl", "Atlanta", mct_same_terminal=25, mct_diff_terminal=45, inter_terminal_walk_minutes=15),
    "DEN": Airport("DEN", "Denver Intl", "Denver", mct_same_terminal=30, mct_diff_terminal=45, inter_terminal_walk_minutes=18),
    "LAX": Airport("LAX", "Los Angeles Intl", "Los Angeles", mct_same_terminal=35, mct_diff_terminal=75, inter_terminal_walk_minutes=30),
    "LHR": Airport("LHR", "London Heathrow", "London", mct_same_terminal=60, mct_diff_terminal=120, inter_terminal_walk_minutes=40),
    "MIA": Airport("MIA", "Miami Intl", "Miami", mct_same_terminal=30, mct_diff_terminal=50, inter_terminal_walk_minutes=20),
}


def _flight_db() -> list[Flight]:
    flights: list[Flight] = [
        # --- JFK -> ORD leg, disrupted by weather ---
        Flight(
            flight_no="AD1402",
            airline="Adapt Air",
            origin="JFK",
            destination="ORD",
            sched_dep=_t(7, 15),
            sched_arr=_t(9, 5),
            terminal_dep="4",
            terminal_arr="2",
            status=FlightStatus.DELAYED,
            delay_minutes=95,
            cause=DisruptionCause.WEATHER,
            raw_ops_note=(
                "AD1402/22AUG GS PGM ZNY RWY CLSD LLWS THUNDERSTORM CELLS 20NM N OF "
                "FIELD EDCT REVISED +95 REF FAA ADVZY ZNY/ORD GROUND STOP 0715-0830Z"
            ),
            gate="B22",
        ),
        # --- ORD -> LAX onward legs (multiple times, for rerouting choices) ---
        Flight(
            flight_no="AD2210",
            airline="Adapt Air",
            origin="ORD",
            destination="LAX",
            sched_dep=_t(9, 50),
            sched_arr=_t(12, 10),
            terminal_dep="3",
            terminal_arr="4",
            status=FlightStatus.ON_TIME,
            gate="C14",
        ),
        Flight(
            flight_no="AD2255",
            airline="Adapt Air",
            origin="ORD",
            destination="LAX",
            sched_dep=_t(12, 30),
            sched_arr=_t(14, 50),
            terminal_dep="3",
            terminal_arr="4",
            status=FlightStatus.ON_TIME,
            gate="C20",
        ),
        Flight(
            flight_no="AD2290",
            airline="Adapt Air",
            origin="ORD",
            destination="LAX",
            sched_dep=_t(16, 0),
            sched_arr=_t(18, 25),
            terminal_dep="3",
            terminal_arr="4",
            status=FlightStatus.ON_TIME,
            gate="C08",
        ),
        Flight(
            flight_no="AD2340",
            airline="Adapt Air",
            origin="ORD",
            destination="LAX",
            sched_dep=_t(19, 45),
            sched_arr=_t(22, 5),
            terminal_dep="3",
            terminal_arr="4",
            status=FlightStatus.ON_TIME,
            gate="C11",
        ),
        # --- DFW -> ATL leg, cancelled (mechanical) ---
        Flight(
            flight_no="AD880",
            airline="Adapt Air",
            origin="DFW",
            destination="ATL",
            sched_dep=_t(8, 0),
            sched_arr=_t(11, 5),
            terminal_dep="A",
            terminal_arr="S",
            status=FlightStatus.CANCELLED,
            delay_minutes=0,
            cause=DisruptionCause.MECHANICAL,
            raw_ops_note=(
                "AD880/22AUG CNX MX AOG APU FAULT CODE 27-31-04 NO SPARE ACFT AVBL DFW "
                "MAINT HOLD REF TECH LOG 880-0822-1 PARTS ETA 18-24HR"
            ),
            gate="A12",
        ),
        # --- Replacement DFW -> ATL flights on other carriers/times ---
        Flight(
            flight_no="AD884",
            airline="Adapt Air",
            origin="DFW",
            destination="ATL",
            sched_dep=_t(13, 15),
            sched_arr=_t(16, 20),
            terminal_dep="A",
            terminal_arr="S",
            status=FlightStatus.ON_TIME,
            gate="A18",
        ),
        Flight(
            flight_no="AD892",
            airline="Adapt Air",
            origin="DFW",
            destination="ATL",
            sched_dep=_t(18, 40),
            sched_arr=_t(21, 45),
            terminal_dep="A",
            terminal_arr="S",
            status=FlightStatus.ON_TIME,
            gate="A22",
        ),
        Flight(
            flight_no="AD905",
            airline="Adapt Air",
            origin="DFW",
            destination="MIA",
            sched_dep=_t(9, 30),
            sched_arr=_t(13, 15),
            terminal_dep="A",
            terminal_arr="D",
            status=FlightStatus.ON_TIME,
            gate="A05",
        ),
        Flight(
            flight_no="AD906",
            airline="Adapt Air",
            origin="MIA",
            destination="ATL",
            sched_dep=_t(14, 30),
            sched_arr=_t(16, 35),
            terminal_dep="D",
            terminal_arr="S",
            status=FlightStatus.ON_TIME,
            gate="D09",
        ),
        # --- ATL -> LHR onward leg (already booked for Maria Gomez's itinerary) ---
        Flight(
            flight_no="AD70",
            airline="Adapt Air",
            origin="ATL",
            destination="LHR",
            sched_dep=_t(19, 30),
            sched_arr=_t(8, 45, day_offset=1),
            terminal_dep="E",
            terminal_arr="5",
            status=FlightStatus.ON_TIME,
            gate="E36",
        ),
        # --- Standalone ORD -> DEN leg, ATC delay, no connection ---
        Flight(
            flight_no="AD514",
            airline="Adapt Air",
            origin="ORD",
            destination="DEN",
            sched_dep=_t(10, 20),
            sched_arr=_t(12, 5),
            terminal_dep="3",
            terminal_arr="B",
            status=FlightStatus.DELAYED,
            delay_minutes=40,
            cause=DisruptionCause.ATC,
            raw_ops_note=(
                "AD514/22AUG ATC EDCT DLY 40MIN REF ZAU TMU VOL/CAPACITY CONSTRAINT "
                "DEN ARR RATE REDUCED WIND 320/28G40"
            ),
            gate="C05",
        ),
    ]
    return flights


def get_flight_db() -> list[Flight]:
    return _flight_db()


def find_flight(flight_no: str) -> Flight | None:
    for f in get_flight_db():
        if f.flight_no.upper() == flight_no.upper():
            return f
    return None


def find_flights(origin: str, destination: str) -> list[Flight]:
    return [
        f
        for f in get_flight_db()
        if f.origin.upper() == origin.upper() and f.destination.upper() == destination.upper()
    ]


def get_itineraries() -> dict[str, Itinerary]:
    db = {f.flight_no: f for f in get_flight_db()}
    itineraries = {
        "ADPT01": Itinerary(
            record_locator="ADPT01",
            passenger_name="John Carter",
            legs=[db["AD1402"], db["AD2210"]],  # JFK->ORD (95min late) -> ORD->LAX (tight)
        ),
        "ADPT02": Itinerary(
            record_locator="ADPT02",
            passenger_name="Maria Gomez",
            legs=[db["AD880"], db["AD70"]],  # DFW->ATL (cancelled) -> ATL->LHR
        ),
        "ADPT03": Itinerary(
            record_locator="ADPT03",
            passenger_name="Sam Lee",
            legs=[db["AD514"]],  # ORD->DEN, ATC delay, single leg
        ),
    }
    return itineraries


def find_itinerary(record_locator: str) -> Itinerary | None:
    return get_itineraries().get(record_locator.upper())


def get_airport(code: str) -> Airport | None:
    return AIRPORTS.get(code.upper())
