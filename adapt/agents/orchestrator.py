"""ADAPT orchestrator: the agentic layer.

Given an itinerary, autonomously decides which tools to run and in what order —
explain any disrupted legs, assess risk on every connection, and pull rerouting
options wherever a leg is cancelled or a connection is high/critical risk. This is
the "agent" in ADAPT-Agent: no step here requires the passenger to ask for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from adapt.agents import connection_risk, disruption_explainer, rerouting
from adapt.data.mock_data import get_airport
from adapt.llm.base import LLMClient
from adapt.models import ConnectionRisk, Flight, Itinerary, RerouteOption, RiskLevel


@dataclass
class RerouteBundle:
    reason: str
    options: list[RerouteOption]
    narrative: str


@dataclass
class AnalysisReport:
    itinerary: Itinerary
    leg_explanations: list[tuple[Flight, str]] = field(default_factory=list)
    connection_risks: list[tuple[ConnectionRisk, str]] = field(default_factory=list)
    reroutes: list[RerouteBundle] = field(default_factory=list)


def run(itinerary: Itinerary, llm: LLMClient) -> AnalysisReport:
    report = AnalysisReport(itinerary=itinerary)

    # 1. Explain every disrupted leg.
    for leg in itinerary.legs:
        if leg.is_disrupted:
            explanation = disruption_explainer.explain(leg, llm)
            report.leg_explanations.append((leg, explanation))

    final_destination = itinerary.final_destination
    final_arrival = itinerary.legs[-1].sched_arr

    # 2. Walk each connection: cancelled inbound legs go straight to rerouting;
    #    otherwise assess risk, and only reroute if risk is high/critical.
    for inbound, outbound in zip(itinerary.legs, itinerary.legs[1:]):
        if inbound.status.value == "CANCELLED":
            reason = f"{inbound.flight_no} ({inbound.origin} -> {inbound.destination}) was cancelled"
            options, narrative = rerouting.recommend(
                origin=inbound.origin,
                destination=final_destination,
                not_before=inbound.sched_dep,
                original_arrival=final_arrival,
                reason=reason,
                llm=llm,
                exclude_flight_no=inbound.flight_no,
            )
            report.reroutes.append(RerouteBundle(reason, options, narrative))
            continue

        airport = get_airport(inbound.destination)
        if airport is None:
            continue

        risk = connection_risk.assess(itinerary, inbound, outbound, airport, llm)
        narrative = connection_risk.describe(risk, llm)
        report.connection_risks.append((risk, narrative))

        if risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            reason = (
                f"the connection to {outbound.flight_no} at {inbound.destination} is "
                f"{risk.risk_level.value.lower()} risk ({round(risk.probability_missed * 100)}% chance of missing it)"
            )
            options, reroute_narrative = rerouting.recommend(
                origin=inbound.destination,
                destination=final_destination,
                not_before=outbound.sched_dep,
                original_arrival=final_arrival,
                reason=reason,
                llm=llm,
                exclude_flight_no=outbound.flight_no,
            )
            report.reroutes.append(RerouteBundle(reason, options, reroute_narrative))

    return report
