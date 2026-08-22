"""Connection Risk Predictor: probability of missing a connection from layover duration,
terminal distance, and estimated walking time.
"""

from __future__ import annotations

import math

from adapt.llm.base import LLMClient
from adapt.models import Airport, ConnectionRisk, Flight, Itinerary, RiskLevel

# Minutes needed to deplane, clear the jet bridge, and start moving toward the next gate.
DEPLANE_BUFFER_MINUTES = 15
# Extra buffer if the connection requires a terminal change (security recheck, train/shuttle, etc).
TERMINAL_CHANGE_BUFFER_MINUTES = 15


def _required_minutes(airport: Airport, same_terminal: bool) -> tuple[float, str]:
    walk = airport.inter_terminal_walk_minutes if not same_terminal else round(airport.inter_terminal_walk_minutes * 0.3)
    transfer_buffer = TERMINAL_CHANGE_BUFFER_MINUTES if not same_terminal else 0
    required = DEPLANE_BUFFER_MINUTES + walk + transfer_buffer
    detail = (
        f"{DEPLANE_BUFFER_MINUTES}min deplane + {walk}min walk"
        + (f" + {transfer_buffer}min terminal transfer" if transfer_buffer else "")
    )
    return required, detail


def _probability_missed(available_minutes: float, required_minutes: float) -> float:
    if available_minutes <= 0:
        return 0.98
    diff = available_minutes - required_minutes
    scale = max(required_minutes * 0.35, 5)
    probability = 1 / (1 + math.exp(diff / scale))
    return round(min(max(probability, 0.01), 0.98), 3)


def _risk_level(probability: float) -> RiskLevel:
    if probability >= 0.75:
        return RiskLevel.CRITICAL
    if probability >= 0.45:
        return RiskLevel.HIGH
    if probability >= 0.2:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def assess(
    itinerary: Itinerary,
    inbound: Flight,
    outbound: Flight,
    connection_airport: Airport,
    llm: LLMClient,
) -> ConnectionRisk:
    available_minutes = (outbound.sched_dep - inbound.actual_arr).total_seconds() / 60
    same_terminal = inbound.terminal_arr == outbound.terminal_dep
    required_minutes, required_detail = _required_minutes(connection_airport, same_terminal)
    probability = _probability_missed(available_minutes, required_minutes)
    level = _risk_level(probability)

    factors = [
        f"Inbound {inbound.flight_no} lands {round(inbound.delay_minutes)}min late "
        f"({'on time' if inbound.delay_minutes == 0 else f'{inbound.delay_minutes}min delay'})",
        f"{round(available_minutes)}min available before {outbound.flight_no} departs",
        f"Required: {required_detail} = {round(required_minutes)}min",
        f"Terminal change: {'no (' + inbound.terminal_arr + ')' if same_terminal else inbound.terminal_arr + ' -> ' + outbound.terminal_dep}",
    ]

    risk = ConnectionRisk(
        itinerary=itinerary,
        inbound=inbound,
        outbound=outbound,
        connection_airport=connection_airport,
        available_minutes=available_minutes,
        required_minutes=required_minutes,
        probability_missed=probability,
        risk_level=level,
        factors=factors,
    )
    return risk


def describe(risk: ConnectionRisk, llm: LLMClient) -> str:
    context = {
        "connection_airport": risk.connection_airport.code,
        "available_minutes": risk.available_minutes,
        "required_minutes": risk.required_minutes,
        "same_terminal": risk.inbound.terminal_arr == risk.outbound.terminal_dep,
        "risk_level": risk.risk_level.value,
        "probability_missed": risk.probability_missed,
    }
    return llm.describe_risk(context)
