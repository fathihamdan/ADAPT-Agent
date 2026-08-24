"""ADAPT-Agent CLI entry point."""

from __future__ import annotations

import typer

from adapt.agents import connection_risk, disruption_explainer, orchestrator, rerouting
from adapt.agents.connections import find_connections
from adapt.data import atlas_source, aviationstack_source
from adapt.data.mock_data import find_flight, find_passenger, get_airport, get_flight_db, get_passengers
from adapt.llm import get_llm_client
from adapt.utils import formatting as fmt
from adapt.utils.env import load_dotenv

load_dotenv()

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

    reroute_source = "Atlas Flight Booking CLI (live search)" if atlas_source.is_available() else "mock schedule only"
    fmt.console.print(f"Rerouting data source: [bold]{reroute_source}[/bold]")
    if not atlas_source.is_available():
        fmt.console.print("Install the atlas-flight CLI to search real alternative flights for rerouting.")

    live_status = "AviationStack (real flight status)" if aviationstack_source.is_available() else "not configured"
    fmt.console.print(f"Live flight tracking: [bold]{live_status}[/bold]")
    if not aviationstack_source.is_available():
        fmt.console.print("Set AVIATIONSTACK_API_KEY to look up real flights with `adapt track`.")


@app.command()
def flights() -> None:
    """List all flights in the mock schedule."""
    fmt.print_flight_table(get_flight_db())


@app.command()
def passengers() -> None:
    """List all sample passengers with a detected self-connect booking."""
    fmt.print_passenger_table(list(get_passengers().values()))


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
def track(flight_iata: str = typer.Argument(..., help="Real IATA flight number, e.g. AA100, BA249")) -> None:
    """Disruption Explainer for a real flight, using live AviationStack data."""
    if not aviationstack_source.is_available():
        fmt.console.print("[red]AVIATIONSTACK_API_KEY is not set — nothing to track against.[/red]")
        raise typer.Exit(code=1)

    flight = aviationstack_source.lookup_flight(flight_iata)
    if flight is None:
        fmt.console.print(f"[red]No live data found for flight '{flight_iata}'.[/red]")
        raise typer.Exit(code=1)

    llm = get_llm_client()
    explanation = disruption_explainer.explain(flight, llm)
    fmt.print_explanation(flight, explanation)


@app.command()
def risk(passenger_id: str = typer.Argument(..., help="Passenger ID, e.g. PSG1001")) -> None:
    """Connection Risk Predictor: probability of missing each detected connection."""
    passenger = find_passenger(passenger_id)
    if passenger is None:
        fmt.console.print(f"[red]No passenger found with ID '{passenger_id}'.[/red]")
        raise typer.Exit(code=1)
    pairs = find_connections(passenger.flights)
    if not pairs:
        fmt.console.print(f"[yellow]{passenger_id} has no detected connection to assess.[/yellow]")
        return

    llm = get_llm_client()
    for inbound, outbound in pairs:
        if inbound.status.value == "CANCELLED":
            fmt.console.print(f"[yellow]{inbound.flight_no} was cancelled — no risk to compute, see `adapt analyze`.[/yellow]")
            continue
        airport = get_airport(inbound.destination)
        if airport is None:
            continue
        assessment = connection_risk.assess(passenger.passenger_id, inbound, outbound, airport, llm)
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
def analyze(passenger_id: str = typer.Argument(..., help="Passenger ID, e.g. PSG1001 or PSG1002")) -> None:
    """Run the full ADAPT agent end-to-end for a passenger: explain, assess risk, reroute."""
    passenger = find_passenger(passenger_id)
    if passenger is None:
        fmt.console.print(f"[red]No passenger found with ID '{passenger_id}'.[/red]")
        raise typer.Exit(code=1)

    fmt.print_banner()
    fmt.console.print(f"[bold]Passenger {passenger.passenger_id}[/bold] — {passenger.name}")
    fmt.print_flight_table(sorted(passenger.flights, key=lambda f: f.sched_dep), title="Booked Flights")

    llm = get_llm_client()
    report = orchestrator.run(passenger, llm)

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
