"""ADAPT-Agent CLI entry point."""

from __future__ import annotations

import typer

from adapt.agents import connection_risk, disruption_explainer, orchestrator, rerouting
from adapt.data.mock_data import find_flight, find_itinerary, get_airport, get_flight_db, get_itineraries
from adapt.llm import get_llm_client
from adapt.utils import formatting as fmt

app = typer.Typer(
    name="adapt",
    help="ADAPT-Agent: Airline Disruption Analysis & Prevention Technology (CLI prototype).",
    no_args_is_help=True,
)


@app.command()
def status() -> None:
    """Show which LLM backend is active."""
    fmt.print_banner()
    llm = get_llm_client()
    fmt.console.print(f"LLM backend: [bold]{llm.name}[/bold]")
    fmt.console.print(
        "Set ANTHROPIC_API_KEY to switch to real Claude-generated explanations."
        if "offline" in llm.name
        else "Using a live model backend."
    )


@app.command()
def flights() -> None:
    """List all flights in the mock schedule."""
    fmt.print_flight_table(get_flight_db())


@app.command()
def itineraries() -> None:
    """List all sample passenger itineraries (PNRs)."""
    fmt.print_itinerary_table(list(get_itineraries().values()))


@app.command()
def explain(flight_no: str = typer.Argument(..., help="Flight number, e.g. AD1402")) -> None:
    """Disruption Explainer: translate a flight's status into plain English."""
    flight = find_flight(flight_no)
    if flight is None:
        fmt.console.print(f"[red]No flight found with number '{flight_no}'.[/red]")
        raise typer.Exit(code=1)

    llm = get_llm_client()
    explanation = disruption_explainer.explain(flight, llm)
    fmt.print_explanation(flight, explanation)


@app.command()
def risk(record_locator: str = typer.Argument(..., help="Itinerary PNR, e.g. ADPT01")) -> None:
    """Connection Risk Predictor: probability of missing each connection in an itinerary."""
    itinerary = find_itinerary(record_locator)
    if itinerary is None:
        fmt.console.print(f"[red]No itinerary found with PNR '{record_locator}'.[/red]")
        raise typer.Exit(code=1)
    if not itinerary.has_connections:
        fmt.console.print(f"[yellow]{record_locator} has a single leg — no connections to assess.[/yellow]")
        return

    llm = get_llm_client()
    for inbound, outbound in zip(itinerary.legs, itinerary.legs[1:]):
        airport = get_airport(inbound.destination)
        if airport is None:
            continue
        assessment = connection_risk.assess(itinerary, inbound, outbound, airport, llm)
        narrative = connection_risk.describe(assessment, llm)
        fmt.print_risk(assessment, narrative)


@app.command()
def reroute(
    origin: str = typer.Argument(..., help="Origin airport code to search from, e.g. ORD"),
    destination: str = typer.Argument(..., help="Destination airport code, e.g. LAX"),
) -> None:
    """Rerouting Recommender: find alternative flights between two airports."""
    llm = get_llm_client()
    now = min(f.sched_dep for f in get_flight_db())
    options, narrative = rerouting.recommend(
        origin=origin.upper(),
        destination=destination.upper(),
        not_before=now,
        original_arrival=now,
        reason=f"you asked for alternatives from {origin.upper()} to {destination.upper()}",
        llm=llm,
    )
    fmt.print_reroute(f"manual search {origin.upper()} -> {destination.upper()}", options, narrative)


@app.command()
def analyze(record_locator: str = typer.Argument(..., help="Itinerary PNR, e.g. ADPT01 or ADPT02")) -> None:
    """Run the full ADAPT agent end-to-end on an itinerary: explain, assess risk, reroute."""
    itinerary = find_itinerary(record_locator)
    if itinerary is None:
        fmt.console.print(f"[red]No itinerary found with PNR '{record_locator}'.[/red]")
        raise typer.Exit(code=1)

    fmt.print_banner()
    fmt.console.print(f"[bold]Itinerary {itinerary.record_locator}[/bold] — {itinerary.passenger_name}")
    fmt.print_flight_table(itinerary.legs, title="Booked Legs")

    llm = get_llm_client()
    report = orchestrator.run(itinerary, llm)

    if report.leg_explanations:
        fmt.print_section("Disruption Explainer")
        for leg, explanation in report.leg_explanations:
            fmt.print_explanation(leg, explanation)
    else:
        fmt.console.print("[green]No disruptions detected on any leg.[/green]")

    if report.connection_risks:
        fmt.print_section("Connection Risk Predictor")
        for connection, narrative in report.connection_risks:
            fmt.print_risk(connection, narrative)

    if report.reroutes:
        fmt.print_section("Rerouting Recommender")
        for bundle in report.reroutes:
            fmt.print_reroute(bundle.reason, bundle.options, bundle.narrative)
    else:
        fmt.console.print("[green]No rerouting needed.[/green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
