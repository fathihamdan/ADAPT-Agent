"""ADAPT-Agent CLI entry point."""

from __future__ import annotations

import typer

from adapt.agents import connection_risk, disruption_explainer, orchestrator, rerouting
from adapt.agents.connections import find_connections
from adapt.atlas_tools import (
    auth_login,
    auth_poll,
    auth_status,
    build_order_command,
    create_order,
    extract_payload,
    list_baggage,
    list_offers,
    list_seats,
    order_status,
    pay_order,
    search_flights,
    select_baggage,
    select_seat,
    verify_offer,
)
from adapt.data import atlas_source, aviationstack_source
from adapt.data.mock_data import find_flight, find_passenger, get_airport, get_flight_db, get_passengers
from adapt.llm import get_llm_client
from adapt.utils import formatting as fmt
from adapt.utils.env import load_dotenv

try:
    from rich.panel import Panel
except ImportError:  # pragma: no cover
    Panel = None  # type: ignore[misc, assignment]

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
def search(
    text: str | None = typer.Option(
        None,
        "--nl",
        help='Natural-language flight request (e.g. "flights from Tokyo to Shanghai on 26 September, 2 adults"). If omitted, you will be prompted.',
    ),
    adults_override: int | None = typer.Option(
        None,
        "--adults",
        help="Override the passenger count parsed from natural language.",
    ),
) -> None:
    """Search Atlas for flights using natural language.

    Describe where you want to go and when; ADAPT extracts origin, destination,
    departure date, and passenger count, then queries the Atlas Flight API.

    If anything is missing, you'll be prompted for it before the search runs.
    """
    from datetime import date

    llm = get_llm_client()
    console = fmt.console

    # --- 1. Get natural-language input -----------------------------------
    if text is None:
        console.print(
            Panel.fit(
                "[bold cyan]ADAPT Flight Search[/bold cyan]\n"
                "[dim]Describe the flight you want in natural language.[/dim]\n"
                "[dim]Examples:[/dim]\n"
                '  [green]"flights from Tokyo to Shanghai on 26 September, 1 adult"[/green]\n'
                '  [green]"direct economy from DFW to LHR next Friday"[/green]\n'
                '  [green]"NYC to London, 2 adults, October 5"[/green]',
                border_style="cyan",
            )
        )
        text = typer.prompt("What flight are you looking for?")
    if not text or not text.strip():
        console.print("[red]No flight description provided.[/red]")
        raise typer.Exit(code=1)

    # --- 2. Parse it through the active LLM backend -----------------------
    with console.status("[bold cyan]Parsing your request...[/bold cyan]"):
        parsed = llm.parse_flight_request(text.strip())

    origin = parsed.get("origin")
    destination = parsed.get("destination")
    depart = parsed.get("depart")
    adults = adults_override or parsed.get("adults", 1)
    missing = list(parsed.get("missing") or [])

    # Show what we understood.
    understood = (
        f"[bold]Origin:[/bold] {origin or '[red]missing[/red]'}   "
        f"[bold]Destination:[/bold] {destination or '[red]missing[/red]'}   "
        f"[bold]Depart:[/bold] {depart or '[red]missing[/red]'}   "
        f"[bold]Adults:[/bold] {adults}"
    )
    console.print(Panel(understood, title="What I understood", border_style="cyan"))

    # --- 3. Re-prompt for anything missing --------------------------------
    for field in missing:
        if field == "origin":
            origin = typer.prompt("Departing from (city or airport code)").strip().upper()
        elif field == "destination":
            destination = typer.prompt("Flying to (city or airport code)").strip().upper()
        elif field == "depart":
            raw = typer.prompt("Departure date (e.g. 26 September, 2026-09-26, next Friday)").strip()
            # Run the raw date through the regex parser to normalise it.
            from adapt.llm.parser import parse_flight_request as _regex_parse

            depart = _regex_parse(f"on {raw}").depart
            if depart is None:
                console.print(f"[red]Could not parse date '{raw}'.[/red]")
                raise typer.Exit(code=1)
            depart = depart.isoformat()

    if not (origin and destination and depart):
        console.print("[red]Cannot search without origin, destination, and departure date.[/red]")
        raise typer.Exit(code=1)

    # --- 4. Authorisation check (non-fatal) -------------------------------
    ticketing_available = False
    try:
        auth = auth_status()
        ticketing_available = bool(
            auth.get("code") == "AUTHORIZED"
            and (auth.get("data") or {}).get("ticketing_available")
        )
    except Exception:
        ticketing_available = False

    # --- 5. Run Atlas search ---------------------------------------------
    with console.status(
        f"[bold cyan]Searching Atlas for {origin} -> {destination} on {depart}...[/bold cyan]"
    ):
        try:
            response = search_flights(
                origin.upper(),
                destination.upper(),
                depart,
                adults,
            )
        except RuntimeError as exc:
            console.print(Panel.fit(
                f"[bold red]Atlas search failed[/bold red]\n{exc}",
                border_style="red",
            ))
            raise typer.Exit(code=1)

    payload = extract_payload(response) or {}
    raw_offers = payload.get("offers", []) or []

    # --- 6. Convert to AtlasOffer records for display ---------------------
    from adapt.atlas import AtlasOffer, AtlasSegment
    from datetime import datetime as _dt

    def _parse_compact(value: str) -> _dt:
        try:
            return _dt.strptime(value, "%Y%m%d%H%M")
        except ValueError:
            return _dt.min

    offers: list = []
    for offer in raw_offers:
        segments = offer.get("segments", []) or []
        if not segments:
            continue
        parsed_segments = [
            AtlasSegment(
                carrier=s.get("carrier", ""),
                operating_carrier=s.get("operating_carrier"),
                flight_number=s.get("flight_number", ""),
                origin=s.get("departure_airport", "").upper(),
                destination=s.get("arrival_airport", "").upper(),
                departure=_parse_compact(s.get("departure_time", "")),
                arrival=_parse_compact(s.get("arrival_time", "")),
                duration_minutes=int(s.get("duration_minutes", 0) or 0),
                cabin_class=int(s.get("cabin_class", 1) or 1),
            )
            for s in segments
        ]
        first = segments[0]
        last = segments[-1]
        prices = offer.get("passenger_prices", []) or []
        total = offer.get("total_price")
        if total is None and prices:
            total = sum(p.get("subtotal", 0.0) for p in prices)
        offers.append(
            AtlasOffer(
                offer_id=offer.get("offer_id", ""),
                search_id=payload.get("search_id", ""),
                carrier=first.get("carrier", ""),
                flight_number=first.get("flight_number", ""),
                origin=first.get("departure_airport", "").upper(),
                destination=last.get("arrival_airport", "").upper(),
                departure=_parse_compact(first.get("departure_time", "")),
                arrival=_parse_compact(last.get("arrival_time", "")),
                duration_minutes=sum(s.duration_minutes for s in parsed_segments),
                cabin_class=int(first.get("cabin_class", 1) or 1),
                currency=offer.get("currency", "USD"),
                total_price=float(total or 0.0),
                base_fare=sum(p.get("base_fare_per_passenger", 0.0) * p.get("count", 1) for p in prices),
                tax=sum(p.get("tax_per_passenger", 0.0) * p.get("count", 1) for p in prices),
                price_status=offer.get("price_status", "reference"),
                bookable=bool(offer.get("bookable", False)),
                ancillary_supported=list(offer.get("ancillary_supported", []) or []),
                operating_carrier=first.get("operating_carrier"),
                segments=parsed_segments,
            )
        )

    # --- 7. Render --------------------------------------------------------
    source = parsed.get("source", "regex")
    fmt.print_atlas_offers(
        origin.upper(),
        destination.upper(),
        depart,
        offers,
        ticketing_available=ticketing_available,
        source_label=source,
    )


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
    use_atlas: bool = typer.Option(
        False,
        "--use-atlas",
        help="Pull live inventory from the Atlas Flight API (falls back to mock data on any failure).",
    ),
    atlas_env: str = typer.Option(
        "production",
        "--atlas-env",
        help="Atlas environment to query: 'production' or 'sandbox'. Switching environments invalidates cached offers.",
    ),
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
        use_atlas=use_atlas,
        atlas_env=atlas_env,
    )
    fmt.print_reroute(f"manual search {origin.upper()} -> {destination.upper()}", options, narrative)


@app.command()
def atlas_auth_status() -> None:
    """Check Atlas authorization state."""
    response = auth_status()
    fmt.console.print(response)


@app.command()
def atlas_auth_login() -> None:
    """Start the Atlas authorization flow."""
    response = auth_login()
    fmt.console.print(response)


@app.command()
def atlas_auth_poll() -> None:
    """Poll Atlas authorization once."""
    response = auth_poll()
    fmt.console.print(response)


@app.command()
def atlas_search(
    origin: str = typer.Argument(..., help="Origin airport code"),
    destination: str = typer.Argument(..., help="Destination airport code"),
    depart: str = typer.Argument(..., help="Departure date in YYYY-MM-DD format"),
    adults: int = typer.Argument(1, help="Passenger count"),
) -> None:
    """Run a search with the Atlas Flight Booking CLI."""
    response = search_flights(origin.upper(), destination.upper(), depart, adults)
    payload = extract_payload(response)
    fmt.console.print(payload)


@app.command()
def atlas_offer_verify(offer_id: str = typer.Argument(..., help="Offer identifier returned by Atlas")) -> None:
    """Verify a flight offer and show the current price."""
    response = verify_offer(offer_id)
    fmt.console.print(extract_payload(response))


@app.command()
def atlas_offer_list(search_id: str = typer.Argument(..., help="Search identifier returned by Atlas")) -> None:
    """List offers for a search."""
    response = list_offers(search_id)
    fmt.console.print(extract_payload(response))


@app.command()
def atlas_baggage_list(booking_id: str = typer.Argument(..., help="Booking identifier")) -> None:
    """List baggage options for a booking."""
    response = list_baggage(booking_id)
    fmt.console.print(extract_payload(response))


@app.command()
def atlas_seat_list(booking_id: str = typer.Argument(..., help="Booking identifier")) -> None:
    """List seat options for a booking."""
    response = list_seats(booking_id)
    fmt.console.print(extract_payload(response))


@app.command()
def atlas_order_create(
    booking_id: str = typer.Argument(..., help="Booking identifier"),
    passengers_source: str = typer.Option("passengers-stdin", help="Use passengers-stdin or passengers-file"),
    passengers_file: str = typer.Option(None, help="Absolute path to a passenger file if needed"),
    seat_policy: str = typer.Option(None, help="Optional seat policy"),
) -> None:
    """Create an Atlas order."""
    response = create_order(booking_id, passengers_source, passengers_file=passengers_file, seat_policy=seat_policy)
    fmt.console.print(extract_payload(response))


@app.command()
def atlas_order_pay(payment_confirmation_id: str = typer.Argument(..., help="Single-use confirmation ID")) -> None:
    """Pay for an Atlas order."""
    response = pay_order(payment_confirmation_id)
    fmt.console.print(extract_payload(response))


@app.command()
def atlas_order_status(order_no: str = typer.Argument(..., help="Atlas order number")) -> None:
    """Check booking or ticketing status."""
    response = order_status(order_no)
    fmt.console.print(extract_payload(response))


@app.command()
def atlas_booking_demo(
    origin: str = typer.Argument(..., help="Origin airport code"),
    destination: str = typer.Argument(..., help="Destination airport code"),
    depart: str = typer.Argument(..., help="Departure date in YYYY-MM-DD format"),
    adults: int = typer.Argument(1, help="Passenger count"),
) -> None:
    """Prototype an end-to-end Atlas booking flow using the CLI wrappers."""
    search = search_flights(origin.upper(), destination.upper(), depart, adults)
    data = extract_payload(search)
    fmt.console.print("[bold]Search result[/bold]")
    fmt.console.print(data)
    if not data:
        return
    search_id = data.get("search_id")
    if search_id:
        offers = list_offers(search_id)
        fmt.console.print("[bold]Offer list[/bold]")
        fmt.console.print(extract_payload(offers))

    booking_id = data.get("booking_id") or "demo-booking-id"
    fmt.console.print("[bold]Command ready[/bold]", build_order_command(booking_id, "passengers-stdin", seat_policy="continue-without-seat"))


@app.command()
def analyze(
    passenger_id: str = typer.Argument(..., help="Passenger ID, e.g. PSG1001 or PSG1002"),
    use_atlas: bool = typer.Option(
        False,
        "--use-atlas",
        help="Pull live reroute inventory from the Atlas Flight API (falls back to mock data on any failure).",
    ),
    atlas_env: str = typer.Option(
        "production",
        "--atlas-env",
        help="Atlas environment to query: 'production' or 'sandbox'.",
    ),
) -> None:
    """Run the full ADAPT agent end-to-end for a passenger: explain, assess risk, reroute."""
    passenger = find_passenger(passenger_id)
    if passenger is None:
        fmt.console.print(f"[red]No passenger found with ID '{passenger_id}'.[/red]")
        raise typer.Exit(code=1)

    fmt.print_banner()
    fmt.console.print(f"[bold]Passenger {passenger.passenger_id}[/bold] — {passenger.name}")
    fmt.print_flight_table(sorted(passenger.flights, key=lambda f: f.sched_dep), title="Booked Flights")

    llm = get_llm_client()
    report = orchestrator.run(
        passenger,
        llm,
        use_atlas=use_atlas,
        atlas_env=atlas_env,
    )

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
        if report.rebooking_plan:
            fmt.print_section("Rebooking Workflow")
            fmt.console.print(report.rebooking_plan)
    else:
        fmt.console.print("[green]No rerouting needed.[/green]")


@app.command()
def rebook(
    origin: str = typer.Argument(..., help="Origin airport code"),
    destination: str = typer.Argument(..., help="Destination airport code"),
    depart: str = typer.Argument(..., help="Departure date in YYYY-MM-DD format"),
    adults: int = typer.Option(1, help="Passenger count"),
    reason: str = typer.Option("customer requested rebooking", help="Reason for the rebooking"),
) -> None:
    """Build a structured Atlas booking workflow for a disruption-driven rebooking."""
    from adapt.agents.rebooking import build_rebooking_plan

    plan = build_rebooking_plan(
        origin=origin.upper(),
        destination=destination.upper(),
        depart=depart,
        adults=adults,
        reason=reason,
    )
    fmt.console.print(plan)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
