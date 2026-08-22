"""Core domain models for ADAPT-Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


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
    terminal_dep: str
    terminal_arr: str
    status: FlightStatus = FlightStatus.ON_TIME
    delay_minutes: int = 0
    cause: DisruptionCause = DisruptionCause.NONE
    raw_ops_note: str = ""  # cryptic airline-ops-style note, source text for the explainer
    gate: str = ""

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
class Itinerary:
    record_locator: str  # PNR
    passenger_name: str
    legs: list[Flight] = field(default_factory=list)

    @property
    def final_destination(self) -> str:
        return self.legs[-1].destination if self.legs else ""

    @property
    def has_connections(self) -> bool:
        return len(self.legs) > 1


@dataclass
class ConnectionRisk:
    itinerary: Itinerary
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
