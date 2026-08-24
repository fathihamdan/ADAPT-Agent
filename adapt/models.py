"""Core domain models for ADAPT-Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class FlightStatus(str, Enum):
    ON_TIME = "ON_TIME"
    DELAYED = "DELAYED"
    CANCELLED = "CANCELLED"
    DIVERTED = "DIVERTED"


class DisruptionCause(str, Enum):
    WEATHER = "WEATHER"
    ATC = "ATC"
    MECHANICAL = "MECHANICAL"
    CREW = "CREW"
    SECURITY = "SECURITY"
    LATE_INBOUND_AIRCRAFT = "LATE_INBOUND_AIRCRAFT"
    NONE = "NONE"
    # Real tracking data (e.g. AviationStack) reports that a flight *is* disrupted
    # without saying why - distinct from NONE, which means no disruption at all.
    UNKNOWN = "UNKNOWN"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class Airport:
    code: str
    name: str
    city: str
    # Minimum connection time in minutes, keyed by "same_terminal" / "diff_terminal"
    mct_same_terminal: int = 30
    mct_diff_terminal: int = 60
    # Average walking time in minutes between terminals (gate-to-gate estimate)
    inter_terminal_walk_minutes: int = 20


@dataclass
class Flight:
    flight_no: str
    airline: str
    origin: str  # airport code
    destination: str  # airport code
    sched_dep: datetime
    sched_arr: datetime
    terminal_dep: str = ""
    terminal_arr: str = ""
    status: FlightStatus = FlightStatus.ON_TIME
    delay_minutes: int = 0
    cause: DisruptionCause = DisruptionCause.NONE
    raw_ops_note: str = ""  # cryptic airline-ops-style note, source text for the explainer
    gate: str = ""
    source: str = "mock"  # "mock" or "atlas" — which data source produced this record

    @property
    def actual_dep(self) -> datetime:
        from datetime import timedelta

        return self.sched_dep + timedelta(minutes=self.delay_minutes)

    @property
    def actual_arr(self) -> datetime:
        from datetime import timedelta

        return self.sched_arr + timedelta(minutes=self.delay_minutes)

    @property
    def is_disrupted(self) -> bool:
        return self.status != FlightStatus.ON_TIME


@dataclass
class Passenger:
    """A dealer's customer and everything they've booked - not an airline PNR.

    `flights` is flat and not required to be pre-ordered or pre-paired: a
    passenger books flight A on one airline and flight B on a different one as
    a self-connect trip, and *whether* two of their flights actually connect is
    something adapt.agents.connections.find_connections() detects, not
    something declared here.
    """

    passenger_id: str  # dealer-issued, e.g. "PSG1001"
    name: str
    flights: list[Flight] = field(default_factory=list)

    @property
    def worst_status(self) -> FlightStatus:
        """The single status that best summarizes this passenger's flights, worst first.

        A shared source of truth for "how disrupted is this passenger overall" -
        CLI and web formatting both need it, and duplicating the priority ordering
        in each place is exactly how DIVERTED once silently fell through to ON_TIME.
        """
        priority = [FlightStatus.CANCELLED, FlightStatus.DIVERTED, FlightStatus.DELAYED]
        for status in priority:
            if any(f.status == status for f in self.flights):
                return status
        return FlightStatus.ON_TIME


@dataclass
class ConnectionRisk:
    passenger_id: str
    inbound: Flight
    outbound: Flight
    connection_airport: Airport
    available_minutes: float
    required_minutes: float
    probability_missed: float  # 0.0 - 1.0
    risk_level: RiskLevel
    factors: list[str] = field(default_factory=list)


@dataclass
class RerouteOption:
    replacement_legs: list[Flight]
    new_arrival: datetime
    delay_vs_original_minutes: int
    connections: int
    notes: str = ""
    # Atlas-only metadata. Populated when the option was produced from a live
    # Atlas search; None when the option came from mock data.
    atlas_offer_id: str | None = None
    atlas_search_id: str | None = None
    atlas_price: float | None = None
    atlas_currency: str | None = None
    atlas_price_status: str | None = None  # "reference" | "current"
    atlas_bookable: bool | None = None
    atlas_ancillary_supported: list[str] | None = None

    @property
    def from_atlas(self) -> bool:
        return self.atlas_offer_id is not None


class BookingStage(str, Enum):
    """Where the booking workflow currently stands."""
    SEARCHING = "SEARCHING"
    VERIFYING = "VERIFYING"
    COLLECTING_PASSENGERS = "COLLECTING_PASSENGERS"
    CREATING_ORDER = "CREATING_ORDER"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    PAYING = "PAYING"
    TICKETED = "TICKETED"
    TICKETING_PENDING = "TICKETING_PENDING"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class BookingResult:
    """Outcome of an Atlas booking workflow execution."""
    stage: BookingStage
    offer_id: str = ""
    booking_id: str = ""
    order_no: str = ""
    payment_confirmation_id: str = ""
    total_price: float = 0.0
    currency: str = "USD"
    price_change: str | None = None  # "unchanged", "decreased", "increased"
    previous_price: float | None = None
    current_price: float | None = None
    order_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)
