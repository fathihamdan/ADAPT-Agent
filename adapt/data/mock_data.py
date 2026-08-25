"""Mock/sample data: airports, a flight database, and sample self-connect passengers.

Every passenger here books flight A on one fictional airline and flight B on a
*different* one - a self-connect trip a 3rd-party ticket dealer sold as one
journey, which is the actual scenario ADAPT-Agent is for. Passengers with only
one flight aren't modeled here at all: there's no connection for this tool to
watch, so there's nothing to build.

Stands in for a real flight-data provider (FlightAware, AviationStack, a dealer's
own booking feed, etc). Swap `get_flight_db()` / `get_passengers()` for real API
calls later — nothing else in the codebase depends on this module being static.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from adapt.data import aviationstack_source
from adapt.models import (
    Airport,
    DisruptionCause,
    Flight,
    FlightStatus,
    Passenger,
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
    # NRT/KIX: real airports covered by Atlas Sandbox's test inventory (Sept 4, 2026
    # only), used so PSG1001's rerouting actually hits the live Atlas API instead of
    # always falling back to mock data.
    "NRT": Airport("NRT", "Narita Intl", "Tokyo", mct_same_terminal=45, mct_diff_terminal=90, inter_terminal_walk_minutes=30),
    "KIX": Airport("KIX", "Kansai Intl", "Osaka", mct_same_terminal=35, mct_diff_terminal=60, inter_terminal_walk_minutes=20),
    # Hubs for the wider self-connect queue (PSG1004+). Walk times drive the risk
    # model directly, so they are the number that matters most here: the sprawling
    # multi-terminal hubs (LHR, DXB, CDG) punish a terminal change hardest.
    "SIN": Airport("SIN", "Changi", "Singapore", mct_same_terminal=45, mct_diff_terminal=75, inter_terminal_walk_minutes=25),
    "FRA": Airport("FRA", "Frankfurt am Main", "Frankfurt", mct_same_terminal=45, mct_diff_terminal=90, inter_terminal_walk_minutes=30),
    "DXB": Airport("DXB", "Dubai Intl", "Dubai", mct_same_terminal=60, mct_diff_terminal=90, inter_terminal_walk_minutes=35),
    "SYD": Airport("SYD", "Kingsford Smith", "Sydney", mct_same_terminal=40, mct_diff_terminal=80, inter_terminal_walk_minutes=30),
    "CDG": Airport("CDG", "Charles de Gaulle", "Paris", mct_same_terminal=50, mct_diff_terminal=100, inter_terminal_walk_minutes=35),
    "HND": Airport("HND", "Haneda", "Tokyo", mct_same_terminal=35, mct_diff_terminal=70, inter_terminal_walk_minutes=25),
}

# Atlas Sandbox's test inventory only exists for this specific date.
ATLAS_SANDBOX_DATE = datetime(2026, 9, 4, 0, 0)


def _flight_db() -> list[Flight]:
    flights: list[Flight] = [
        # === PSG1001: Northbridge Air -> Kansai Wing, self-connect at NRT ===
        Flight(
            flight_no="NA1402",
            airline="Northbridge Air",
            origin="JFK",
            destination="NRT",
            sched_dep=ATLAS_SANDBOX_DATE.replace(hour=6, minute=0),
            sched_arr=ATLAS_SANDBOX_DATE.replace(hour=8, minute=15),
            terminal_dep="4",
            terminal_arr="1",
            status=FlightStatus.DELAYED,
            delay_minutes=95,
            cause=DisruptionCause.WEATHER,
            raw_ops_note=(
                "NA1402/04SEP GS PGM ZNY RWY CLSD LLWS THUNDERSTORM CELLS 20NM N OF "
                "FIELD EDCT REVISED +95 REF FAA ADVZY ZNY/NRT GROUND STOP 0600-0715Z"
            ),
            gate="B22",
        ),
        # Different airline, ticketed separately by the dealer - a real Atlas
        # Sandbox route (Sept 4, 2026 only), so this connection's rerouting search
        # hits the live Atlas API instead of falling back to mock data.
        Flight(
            flight_no="KW210",
            airline="Kansai Wing",
            origin="NRT",
            destination="KIX",
            # A legitimately bookable connection: 75min scheduled buffer, just
            # over NRT's diff-terminal minimum (60min) - tight by design, but
            # only becomes truly critical once NA1402's 95min delay hits it.
            sched_dep=ATLAS_SANDBOX_DATE.replace(hour=9, minute=30),
            sched_arr=ATLAS_SANDBOX_DATE.replace(hour=11, minute=5),
            terminal_dep="2",
            terminal_arr="1",
            status=FlightStatus.ON_TIME,
            gate="42",
        ),
        # === PSG1002: Northbridge Air -> Skyline Connect, self-connect at ATL ===
        Flight(
            flight_no="NA880",
            airline="Northbridge Air",
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
                "NA880/22AUG CNX MX AOG APU FAULT CODE 27-31-04 NO SPARE ACFT AVBL DFW "
                "MAINT HOLD REF TECH LOG 880-0822-1 PARTS ETA 18-24HR"
            ),
            gate="A12",
        ),
        # Replacement Northbridge DFW->ATL options, for the mock rerouting fallback.
        Flight(
            flight_no="NA884",
            airline="Northbridge Air",
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
            flight_no="NA892",
            airline="Northbridge Air",
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
            flight_no="NA905",
            airline="Northbridge Air",
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
            flight_no="NA906",
            airline="Northbridge Air",
            origin="MIA",
            destination="ATL",
            sched_dep=_t(14, 30),
            sched_arr=_t(16, 35),
            terminal_dep="D",
            terminal_arr="S",
            status=FlightStatus.ON_TIME,
            gate="D09",
        ),
        # Different airline, ticketed separately by the dealer.
        Flight(
            flight_no="SC070",
            airline="Skyline Connect",
            origin="ATL",
            destination="LHR",
            sched_dep=_t(19, 30),
            sched_arr=_t(8, 45, day_offset=1),
            terminal_dep="E",
            terminal_arr="5",
            status=FlightStatus.ON_TIME,
            gate="E36",
        ),
        # === PSG1003: Northbridge Air -> Skyline Connect, self-connect at DEN ===
        # A comfortable-buffer pair, on purpose - the queue should show a range of
        # risk, not only crises.
        Flight(
            flight_no="NA514",
            airline="Northbridge Air",
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
                "NA514/22AUG ATC EDCT DLY 40MIN REF ZAU TMU VOL/CAPACITY CONSTRAINT "
                "DEN ARR RATE REDUCED WIND 320/28G40"
            ),
            gate="C05",
        ),
        # Different airline, ticketed separately by the dealer.
        Flight(
            flight_no="SC118",
            airline="Skyline Connect",
            origin="DEN",
            destination="LAX",
            sched_dep=_t(13, 45),
            sched_arr=_t(15, 20),
            terminal_dep="A",
            terminal_arr="4",
            status=FlightStatus.ON_TIME,
            gate="A31",
        ),
        # === PSG1004: Meridian Atlantic -> Albion Express, self-connect at LHR ===
        # CRITICAL. Booked with exactly LHR's 120min diff-terminal minimum, which a
        # 95min late inbound demolishes: 25min left against 70min of walking and
        # security. The most common way a self-connect dies - the booking was fine.
        Flight(
            flight_no="MA318",
            airline="Meridian Atlantic",
            origin="CDG",
            destination="LHR",
            sched_dep=_t(12, 25),
            sched_arr=_t(13, 40),
            terminal_dep="2E",
            terminal_arr="2",
            status=FlightStatus.DELAYED,
            delay_minutes=95,
            cause=DisruptionCause.LATE_INBOUND_AIRCRAFT,
            raw_ops_note=(
                "MA318/25AUG DLY 95MIN RTN INBD ACFT AOG CDG ROTATION SLIP REF "
                "MSN2214 CREW DUTY WITHIN LIMITS NO SUB ACFT AVBL"
            ),
            gate="K42",
        ),
        Flight(
            flight_no="AE774",
            airline="Albion Express",
            origin="LHR",
            destination="DXB",
            sched_dep=_t(15, 40),
            sched_arr=_t(1, 40, 1),
            terminal_dep="5",
            terminal_arr="3",
            status=FlightStatus.ON_TIME,
            gate="A14",
        ),
        # === PSG1005: Coral Pacific -> Silverwing, self-connect at SIN ===
        # HIGH. 45min against 55min required - under water, but only just, so the
        # passenger might still make it at a run. Exactly the ambiguous case an ops
        # desk needs a probability for rather than a yes/no.
        Flight(
            flight_no="QN512",
            airline="Coral Pacific",
            origin="SYD",
            destination="SIN",
            sched_dep=_t(9, 30),
            sched_arr=_t(16, 15),
            terminal_dep="1",
            terminal_arr="1",
            status=FlightStatus.DELAYED,
            delay_minutes=50,
            cause=DisruptionCause.ATC,
            raw_ops_note=(
                "QN512/25AUG ATC FLOW CTL WSSS ARR SEQ DLY 50MIN REF SINGAPORE FIR "
                "TMA SATURATION HOLDING PATTERN VMR 2 ORBITS"
            ),
            gate="34",
        ),
        Flight(
            flight_no="SW880",
            airline="Silverwing",
            origin="SIN",
            destination="FRA",
            sched_dep=_t(17, 50),
            sched_arr=_t(1, 30, 1),
            terminal_dep="3",
            terminal_arr="1",
            status=FlightStatus.ON_TIME,
            gate="B08",
        ),
        # === PSG1006: Rhineland Air -> Kestrel Pacific, self-connect at FRA ===
        # MEDIUM. 75min against 60min required: makeable, but with no margin for a
        # gate change or a slow bag. Worth watching, not worth rebooking yet.
        Flight(
            flight_no="RL220",
            airline="Rhineland Air",
            origin="LHR",
            destination="FRA",
            sched_dep=_t(7, 10),
            sched_arr=_t(9, 30),
            terminal_dep="2",
            terminal_arr="1",
            status=FlightStatus.DELAYED,
            delay_minutes=30,
            cause=DisruptionCause.CREW,
            raw_ops_note=(
                "RL220/25AUG DLY 30MIN CREW POSITIONING FO OUT OF HOURS AWAITING "
                "STANDBY EX LHR CREW HOTEL TRANSFER IN PROGRESS"
            ),
            gate="B31",
        ),
        Flight(
            flight_no="KP640",
            airline="Kestrel Pacific",
            origin="FRA",
            destination="HND",
            sched_dep=_t(11, 15),
            sched_arr=_t(6, 30, 1),
            terminal_dep="2",
            terminal_arr="3",
            status=FlightStatus.ON_TIME,
            gate="D07",
        ),
        # === PSG1007: Gulfstream Regional -> Piedmont Skyways, self-connect at ATL ===
        # LOW. On time, same terminal, 95min buffer. The queue must contain trips
        # that are simply fine, or "sorted worst-first" means nothing.
        Flight(
            flight_no="GR114",
            airline="Gulfstream Regional",
            origin="MIA",
            destination="ATL",
            sched_dep=_t(13, 5),
            sched_arr=_t(15, 10),
            terminal_dep="N",
            terminal_arr="S",
            status=FlightStatus.ON_TIME,
            gate="C19",
        ),
        Flight(
            flight_no="PS402",
            airline="Piedmont Skyways",
            origin="ATL",
            destination="DEN",
            sched_dep=_t(16, 45),
            sched_arr=_t(18, 10),
            terminal_dep="S",
            terminal_arr="A",
            status=FlightStatus.ON_TIME,
            gate="B26",
        ),
        # === PSG1008: Cascade Air -> Skyline Connect, self-connect at DEN ===
        # Cancelled first leg. The layover arithmetic is irrelevant here - there is
        # no inbound aircraft at all - so this exercises the rerouting path rather
        # than the risk model. ORD->LAX has mock alternatives (NA514 + SC118).
        Flight(
            flight_no="CA330",
            airline="Cascade Air",
            origin="ORD",
            destination="DEN",
            sched_dep=_t(9, 45),
            sched_arr=_t(11, 35),
            terminal_dep="2",
            terminal_arr="A",
            status=FlightStatus.CANCELLED,
            cause=DisruptionCause.MECHANICAL,
            raw_ops_note=(
                "CA330/25AUG CNL ACFT AOG HYD SYS 2 LEAK NOSE GEAR RETRACT TEST FAIL "
                "NO SUB ACFT ORD PAX REACCOM REQD"
            ),
            gate="E12",
        ),
        # === PSG1009: Summit Air -> Great Lakes Air, self-connect at ORD ===
        # Already missed: the inbound diverted and lands 15min *after* the onward
        # flight departs. Negative available time is its own edge case - the risk
        # model should say 98%, not crash or round it away.
        Flight(
            flight_no="SM615",
            airline="Summit Air",
            origin="LAX",
            destination="ORD",
            sched_dep=_t(6, 30),
            sched_arr=_t(12, 25),
            terminal_dep="6",
            terminal_arr="1",
            status=FlightStatus.DIVERTED,
            delay_minutes=120,
            cause=DisruptionCause.WEATHER,
            raw_ops_note=(
                "SM615/25AUG DVT MKE WX ORD TSTM CB LINE FIELD BLO MINS DIVERTED "
                "FUEL STATE MIN REFUEL AND CONTINUE ETA ORD +120MIN"
            ),
            gate="TBD",
        ),
        Flight(
            flight_no="GL228",
            airline="Great Lakes Air",
            origin="ORD",
            destination="JFK",
            sched_dep=_t(14, 10),
            sched_arr=_t(17, 25),
            terminal_dep="3",
            terminal_arr="4",
            status=FlightStatus.ON_TIME,
            gate="L23",
        ),
        # === PSG1010: Gulf Meridian -> Indus Star, self-connect at DXB ===
        # MEDIUM, and the connection crosses midnight: the inbound lands at 00:00
        # and the onward leg departs 01:15 the next calendar day. Anything that
        # compares dates rather than instants gets this wrong.
        Flight(
            flight_no="GM907",
            airline="Gulf Meridian",
            origin="FRA",
            destination="DXB",
            sched_dep=_t(17, 20),
            sched_arr=_t(23, 40),
            terminal_dep="1",
            terminal_arr="1",
            status=FlightStatus.DELAYED,
            delay_minutes=20,
            cause=DisruptionCause.SECURITY,
            raw_ops_note=(
                "GM907/25AUG DLY 20MIN SEC SCREEN RESET T1 HOLD BAG RECONCILIATION "
                "PAX OFFLOAD 2 BAGS REMOVED REF SEC ADVZY FRA"
            ),
            gate="A52",
        ),
        Flight(
            flight_no="IS310",
            airline="Indus Star",
            origin="DXB",
            destination="SIN",
            sched_dep=_t(1, 15, 1),
            sched_arr=_t(13, 5, 1),
            terminal_dep="3",
            terminal_arr="1",
            status=FlightStatus.ON_TIME,
            gate="C31",
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


def _override_first_flight(passenger: Passenger, arr_iata: str) -> None:
    """Swap a passenger's first (disrupted) flight for a real, currently-disrupted
    one landing at `arr_iata`, when AviationStack has one available - constrains
    the search so the real flight still geographically connects to the existing
    second flight, and re-dates that second flight to follow the real flight's
    actual date (keeping its original time-of-day) so the connection stays
    chronologically coherent instead of spanning a multi-week gap. Fictional
    passenger, real flight - best-effort, silently keeps both flights fictional
    on any failure.
    """
    if not aviationstack_source.is_available():
        return
    real = aviationstack_source.find_disrupted_flight(arr_iata=arr_iata)
    if not real:
        return

    second_flight = passenger.flights[1]
    new_dep = datetime.combine(real.actual_arr.date(), second_flight.sched_dep.time())
    if new_dep <= real.actual_arr:
        new_dep += timedelta(days=1)
    duration = second_flight.sched_arr - second_flight.sched_dep

    passenger.flights[0] = real
    passenger.flights[1] = replace(second_flight, sched_dep=new_dep, sched_arr=new_dep + duration)


def _build_passengers() -> dict[str, Passenger]:
    db = {f.flight_no: f for f in get_flight_db()}
    passengers = {
        "PSG1001": Passenger(
            passenger_id="PSG1001",
            name="John Carter",
            # Stays fictional-but-Atlas-linked: flight B (NRT->KIX) is pinned to
            # Sept 4 2026 so Atlas Sandbox's rerouting search keeps working -
            # swapping flight A for "today's" real data would connect across a
            # multi-week gap, so we don't do that here (see module docs above).
            flights=[db["NA1402"], db["KW210"]],  # JFK->NRT (95min late) -> NRT->KIX (tight)
        ),
        "PSG1002": Passenger(
            passenger_id="PSG1002",
            name="Maria Gomez",
            flights=[db["NA880"], db["SC070"]],  # DFW->ATL (cancelled) -> ATL->LHR
        ),
        "PSG1003": Passenger(
            passenger_id="PSG1003",
            name="Sam Lee",
            flights=[db["NA514"], db["SC118"]],  # ORD->DEN (40min late) -> DEN->LAX (comfortable)
        ),
        # The wider queue. Each of these targets a specific band of the risk model
        # so the triage list spans LOW through CRITICAL rather than clustering -
        # a queue where every row is red tells an ops desk nothing about priority.
        "PSG1004": Passenger(
            passenger_id="PSG1004",
            name="Priya Raghunathan",
            flights=[db["MA318"], db["AE774"]],  # CDG->LHR (95min late) -> LHR->DXB (CRITICAL)
        ),
        "PSG1005": Passenger(
            passenger_id="PSG1005",
            name="Tomas Novak",
            flights=[db["QN512"], db["SW880"]],  # SYD->SIN (50min late) -> SIN->FRA (HIGH)
        ),
        "PSG1006": Passenger(
            passenger_id="PSG1006",
            name="Amara Okafor",
            flights=[db["RL220"], db["KP640"]],  # LHR->FRA (30min late) -> FRA->HND (MEDIUM)
        ),
        "PSG1007": Passenger(
            passenger_id="PSG1007",
            name="Daniel Whitfield",
            flights=[db["GR114"], db["PS402"]],  # MIA->ATL (on time) -> ATL->DEN (LOW)
        ),
        "PSG1008": Passenger(
            passenger_id="PSG1008",
            name="Hana Kobayashi",
            flights=[db["CA330"], db["SC118"]],  # ORD->DEN (CANCELLED) -> DEN->LAX (reroute)
        ),
        "PSG1009": Passenger(
            passenger_id="PSG1009",
            name="Marcus Delgado",
            flights=[db["SM615"], db["GL228"]],  # LAX->ORD (DIVERTED) -> ORD->JFK (already missed)
        ),
        "PSG1010": Passenger(
            passenger_id="PSG1010",
            name="Yusuf Rahman",
            flights=[db["GM907"], db["IS310"]],  # FRA->DXB (20min late) -> DXB->SIN (over midnight)
        ),
    }

    _override_first_flight(passengers["PSG1002"], arr_iata="ATL")

    return passengers


# Built once (including the live AviationStack lookups) and reused after that -
# a long-running web server would otherwise re-hit the live API on every request.
# Only refresh_passengers() rebuilds it; a CLI invocation is a fresh process each
# run anyway, so it naturally gets one live build per run without any extra code.
_passengers_cache: dict[str, Passenger] | None = None


def get_passengers() -> dict[str, Passenger]:
    global _passengers_cache
    if _passengers_cache is None:
        _passengers_cache = _build_passengers()
    return _passengers_cache


def refresh_passengers() -> dict[str, Passenger]:
    """Force a rebuild, including fresh live AviationStack lookups - the manual
    refresh path, as opposed to get_passengers()'s cached-after-first-build default.
    """
    global _passengers_cache
    _passengers_cache = _build_passengers()
    return _passengers_cache


def find_passenger(passenger_id: str) -> Passenger | None:
    return get_passengers().get(passenger_id.upper())


def get_airport(code: str) -> Airport | None:
    return AIRPORTS.get(code.upper())
