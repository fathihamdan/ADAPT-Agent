"""Rich-based rendering helpers for the CLI."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from adapt.models import ConnectionRisk, Flight, Itinerary, RerouteOption, RiskLevel

console = Console()

_STATUS_STYLE = {
    "ON_TIME": "green",
    "DELAYED": "yellow",
    "CANCELLED": "bold red",
    "DIVERTED": "bold red",
}

_RISK_STYLE = {
    RiskLevel.LOW: "green",
    RiskLevel.MEDIUM: "yellow",
    RiskLevel.HIGH: "bold orange3",
    RiskLevel.CRITICAL: "bold red",
}


def print_banner() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]ADAPT[/bold cyan]  Airline Disruption Analysis & Prevention Technology\n"
            "[dim]Agentic AI-powered disruption management[/dim]",
            border_style="cyan",
        )
    )


def flight_row_style(flight: Flight) -> str:
    return _STATUS_STYLE.get(flight.status.value, "white")


def print_flight_table(flights: list[Flight], title: str = "Flights") -> None:
    table = Table(title=title, header_style="bold cyan")
    table.add_column("Flight")
    table.add_column("Route")
    table.add_column("Sched Dep")
    table.add_column("Sched Arr")
    table.add_column("Status")
    table.add_column("Delay")
    table.add_column("Cause")

    for f in flights:
        style = flight_row_style(f)
        table.add_row(
            f.flight_no,
            f"{f.origin} -> {f.destination}",
            f.sched_dep.strftime("%a %H:%M"),
            f.sched_arr.strftime("%a %H:%M"),
            Text(f.status.value, style=style),
            f"{f.delay_minutes}min" if f.delay_minutes else "-",
            f.cause.value if f.cause.value != "NONE" else "-",
        )
    console.print(table)


def print_itinerary_table(itineraries: list[Itinerary]) -> None:
    table = Table(title="Itineraries", header_style="bold cyan")
    table.add_column("PNR")
    table.add_column("Passenger")
    table.add_column("Route")
    table.add_column("Legs")
    table.add_column("Status")

    for it in itineraries:
        route = " -> ".join([it.legs[0].origin] + [leg.destination for leg in it.legs]) if it.legs else "-"
        worst = "ON_TIME"
        for leg in it.legs:
            if leg.status.value == "CANCELLED":
                worst = "CANCELLED"
                break
            if leg.status.value == "DELAYED" and worst != "CANCELLED":
                worst = "DELAYED"
        style = _STATUS_STYLE.get(worst, "white")
        table.add_row(
            it.record_locator,
            it.passenger_name,
            route,
            " + ".join(leg.flight_no for leg in it.legs),
            Text(worst, style=style),
        )
    console.print(table)


def print_explanation(flight: Flight, explanation: str) -> None:
    style = flight_row_style(flight)
    header = f"[{style}]{flight.flight_no}[/{style}] {flight.origin} -> {flight.destination}  ({flight.status.value})"
    console.print(Panel(explanation, title=header, border_style=style, title_align="left"))


def print_risk(risk: ConnectionRisk, narrative: str) -> None:
    style = _RISK_STYLE.get(risk.risk_level, "white")
    header = (
        f"Connection at {risk.connection_airport.code}: "
        f"{risk.inbound.flight_no} -> {risk.outbound.flight_no}  "
        f"[{style}]{risk.risk_level.value}[/{style}] ({round(risk.probability_missed * 100)}%)"
    )
    body = narrative + "\n\n" + "\n".join(f"  - {f}" for f in risk.factors)
    console.print(Panel(body, title=header, border_style=style, title_align="left"))


def print_reroute(reason: str, options: list[RerouteOption], narrative: str) -> None:
    console.print(Panel.fit(f"[bold]Rerouting triggered:[/bold] {reason}", border_style="magenta"))
    if options:
        table = Table(header_style="bold magenta")
        table.add_column("#")
        table.add_column("Flights")
        table.add_column("New Arrival")
        table.add_column("vs Original")
        table.add_column("Connections")
        for i, opt in enumerate(options, start=1):
            delay_text = f"{opt.delay_vs_original_minutes:+d}min"
            delay_style = "green" if opt.delay_vs_original_minutes <= 0 else "yellow"
            table.add_row(
                str(i),
                " + ".join(l.flight_no for l in opt.replacement_legs) + (f" ({opt.notes})" if opt.notes else ""),
                opt.new_arrival.strftime("%a %H:%M"),
                Text(delay_text, style=delay_style),
                str(opt.connections),
            )
        console.print(table)
    console.print(Panel(narrative, border_style="magenta", title="ADAPT Recommendation", title_align="left"))


def print_section(title: str) -> None:
    console.rule(f"[bold cyan]{title}[/bold cyan]")
