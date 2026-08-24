"""ADAPT orchestrator: the agentic layer.

Given a passenger's flat, possibly cross-airline flight list, autonomously
decides which tools to run and in what order — explain any disrupted flights,
detect and assess risk on every real connection, and pull rerouting options
wherever a flight is cancelled or a connection is high/critical risk. This is
the "agent" in ADAPT-Agent: no step here requires anyone to ask for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from adapt.agents import connection_risk, disruption_explainer, rebooking, rerouting
from adapt.agents.connections import find_connections
from adapt.data.mock_data import get_airport
from adapt.llm.base import LLMClient
from adapt.models import ConnectionRisk, Flight, Passenger, RerouteOption, RiskLevel


@dataclass
class RerouteBundle:
    reason: str
    options: list[RerouteOption]
    narrative: str


@dataclass
class AnalysisReport:
    passenger: Passenger
    leg_explanations: list[tuple[Flight, str]] = field(default_factory=list)
    connection_risks: list[tuple[ConnectionRisk, str]] = field(default_factory=list)
    reroutes: list[RerouteBundle] = field(default_factory=list)
    rebooking_plan: dict | None = None


def run(
    passenger: Passenger,
    llm: LLMClient,
    *,
    use_atlas: bool = False,
    atlas_env: str = "production",
) -> AnalysisReport:
    report = AnalysisReport(passenger=passenger)

    # 1. Explain every disrupted flight.
    for f in passenger.flights:
        if f.is_disrupted:
            explanation = disruption_explainer.explain(f, llm)
            report.leg_explanations.append((f, explanation))

    if not passenger.flights:
        return report

    # A passenger record is one self-connect journey, so the last flight in
    # chronological order is where they're ultimately trying to get to -
    # rerouting always aims for that, regardless of which leg is disrupted.
    ordered_flights = sorted(passenger.flights, key=lambda f: f.sched_dep)
    final_destination = ordered_flights[-1].destination
    final_arrival = ordered_flights[-1].sched_arr

    # 2. Walk each detected connection: cancelled inbound flights go straight to
    #    rerouting; otherwise assess risk, and only reroute if risk is high/critical.
    for inbound, outbound in find_connections(passenger.flights):
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
                use_atlas=use_atlas,
                atlas_env=atlas_env,
            )
            report.reroutes.append(RerouteBundle(reason, options, narrative))
            report.rebooking_plan = rebooking.build_rebooking_plan(
                origin=inbound.origin,
                destination=final_destination,
                depart=inbound.sched_dep.strftime("%Y-%m-%d"),
                adults=1,
                reason=reason,
            )
            continue

        airport = get_airport(inbound.destination)
        if airport is None:
            continue

        risk = connection_risk.assess(passenger.passenger_id, inbound, outbound, airport, llm)
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
                use_atlas=use_atlas,
                atlas_env=atlas_env,
            )
            report.reroutes.append(RerouteBundle(reason, options, reroute_narrative))
            report.rebooking_plan = rebooking.build_rebooking_plan(
                origin=inbound.destination,
                destination=final_destination,
                depart=outbound.sched_dep.strftime("%Y-%m-%d"),
                adults=1,
                reason=reason,
            )

    return report
