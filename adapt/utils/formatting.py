"""Rich-based rendering helpers for the CLI."""

from __future__ import annotations

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from adapt.agents.connections import find_connections
from adapt.models import ConnectionRisk, Flight, Passenger, RerouteOption, RiskLevel

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


def print_passenger_table(passengers: list[Passenger]) -> None:
    """Only passengers with a detected connection are shown - a single-flight
    booking has no connection risk for this tool to watch."""
    table = Table(title="Passengers", header_style="bold cyan")
    table.add_column("Passenger ID")
    table.add_column("Name")
    table.add_column("Route")
    table.add_column("Flights")
    table.add_column("Status")

    for p in passengers:
        if not find_connections(p.flights):
            continue
        ordered = sorted(p.flights, key=lambda f: f.sched_dep)
        route = " -> ".join([ordered[0].origin] + [f.destination for f in ordered])
        worst = p.worst_status.value
        style = _STATUS_STYLE.get(worst, "white")
        table.add_row(
            p.passenger_id,
            p.name,
            route,
            " + ".join(f.flight_no for f in ordered),
            Text(worst, style=style),
        )
    console.print(table)


def print_explanation(flight: Flight, explanation: str) -> None:
    style = flight_row_style(flight)
    header = f"[{style}]{flight.flight_no}[/{style}] {flight.origin} -> {flight.destination}  ({flight.status.value})"
    console.print(Panel(Markdown(explanation), title=header, border_style=style, title_align="left"))


def print_risk(risk: ConnectionRisk, narrative: str) -> None:
    style = _RISK_STYLE.get(risk.risk_level, "white")
    header = (
        f"Connection at {risk.connection_airport.code}: "
        f"{risk.inbound.flight_no} -> {risk.outbound.flight_no}  "
        f"[{style}]{risk.risk_level.value}[/{style}] ({round(risk.probability_missed * 100)}%)"
    )
    factors_text = Text("\n".join(f"  - {f}" for f in risk.factors), style="dim")
    body = Group(Markdown(narrative), Text(""), factors_text)
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
    console.print(Panel(Markdown(narrative), border_style="magenta", title="ADAPT Recommendation", title_align="left"))


def print_section(title: str) -> None:
    console.rule(f"[bold cyan]{title}[/bold cyan]")


def print_atlas_offers(
    origin: str,
    destination: str,
    depart_date: str,
    offers,
    *,
    ticketing_available: bool,
    source_label: str = "llm",
) -> None:
    """Render a list of `AtlasOffer` records as a Rich table.

    `ticketing_available` gates the bookable-vs-reference labelling so users
    see the right expectation even when their account could in principle book.
    """
    console.print(
        Panel.fit(
            f"[bold]Atlas Flight Search[/bold]: {origin} -> {destination} on {depart_date}\n"
            f"[dim]Parser: {source_label}[/dim]",
            border_style="cyan",
        )
    )

    if not offers:
        console.print(
            Panel(
                f"[yellow]Atlas returned no offers for {origin} -> {destination} on "
                f"{depart_date}.[/yellow]\n"
                "Try a different date, a nearby alternate airport, or a more "
                "flexible departure time.",
                title="No results",
                border_style="yellow",
            )
        )
        return

    table = Table(header_style="bold cyan", show_lines=False)
    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("Flights")
    table.add_column("Dep -> Arr")
    table.add_column("Duration")
    table.add_column("Stops", justify="center")
    table.add_column("Total")
    table.add_column("Status")

    for i, offer in enumerate(offers, start=1):
        dep_str = offer.departure.strftime("%a %H:%M") if offer.departure else "-"
        arr_str = offer.arrival.strftime("%a %H:%M") if offer.arrival else "-"
        next_day = (
            "+1" if offer.arrival and offer.departure
            and offer.arrival.date() > offer.departure.date()
            else ""
        )
        hours, mins = divmod(offer.duration_minutes, 60)
        duration = f"{hours}h {mins:02d}m"
        connections = offer.connections
        stops_text = "direct" if connections == 0 else f"{connections} stop{'s' if connections > 1 else ''}"

        price = f"{offer.total_price:.2f} {offer.currency}"
        if offer.is_reference_only or not ticketing_available:
            status = "[yellow]compare only[/yellow]"
        else:
            status = "[green]bookable[/green]"

        table.add_row(
            str(i),
            offer.legs_summary(),
            f"{dep_str} -> {arr_str}{next_day}",
            duration,
            stops_text,
            price,
            status,
        )
    console.print(table)

    if not ticketing_available:
        console.print(
            "[yellow]Ticketing is not active on this Atlas account — offers above "
            "are for comparison only.[/yellow]\n"
            "Complete the activation in the ATRIP workspace, then re-run this "
            "search to unlock price verification and booking."
        )
    elif any(o.is_reference_only for o in offers):
        console.print(
            "[yellow]Some offers are marked 'compare only' — they cannot be "
            "continued to price verification.[/yellow]"
        )
