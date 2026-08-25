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
from adapt.data import atlas_source, aviationstack_source, flight_store, http_cache
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

    # --- 2b. Regex safety net: fill gaps the LLM missed -------------------
    if missing:
        from adapt.llm.parser import parse_flight_request as _regex_parse

        regex_result = _regex_parse(text.strip())
        if not origin and regex_result.origin:
            origin = regex_result.origin
            missing = [m for m in missing if m != "origin"]
        if not destination and regex_result.destination:
            destination = regex_result.destination
            missing = [m for m in missing if m != "destination"]
        if not depart and regex_result.depart:
            depart = regex_result.depart.isoformat()
            missing = [m for m in missing if m != "depart"]

    # Show what we understood.
    understood = (
        f"[bold]Origin:[/bold] {origin or '[red]missing[/red]'}   "
        f"[bold]Destination:[/bold] {destination or '[red]missing[/red]'}   "
        f"[bold]Depart:[/bold] {depart or '[red]missing[/red]'}   "
        f"[bold]Adults:[/bold] {adults}"
    )
    console.print(Panel(understood, title="What I understood", border_style="cyan"))

    # --- 3. Re-prompt for anything missing --------------------------------
    from adapt.llm.parser import _resolve_airport as _resolve

    for field in missing:
        if field == "origin":
            raw = typer.prompt("Departing from (city or airport code)").strip()
            origin = _resolve(raw) or raw.upper()
        elif field == "destination":
            raw = typer.prompt("Flying to (city or airport code)").strip()
            destination = _resolve(raw) or raw.upper()
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

    # --- 4. Authorisation check -------------------------------------------
    ticketing_available = False
    try:
        auth = auth_status()
        auth_code = auth.get("code", "")
        if auth_code != "AUTHORIZED":
            console.print(Panel.fit(
                f"[bold red]Atlas authorization required[/bold red]\n"
                f"Your account is not authorized (status: {auth_code}).\n\n"
                "Run [bold]adapt atlas-auth-login[/bold] and open the link in your browser,\n"
                "then run [bold]adapt atlas-auth-poll[/bold] after signing in.\n\n"
                "You can also run [bold]adapt atlas-auth-status[/bold] to check current state.",
                border_style="red",
            ))
            raise typer.Exit(code=1)
        ticketing_available = bool(
            (auth.get("data") or {}).get("ticketing_available")
        )
    except (RuntimeError, typer.Exit) as exc:
        # Re-raise typer.Exit so the auth-required message propagates.
        if isinstance(exc, typer.Exit):
            raise
        console.print(Panel.fit(
            "[bold red]Atlas CLI unavailable[/bold red]\n"
            "Cannot check authorization. Ensure atlas-flight is installed.",
            border_style="red",
        ))
        raise typer.Exit(code=1)

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

    # Check for auth or error codes in the response envelope
    resp_code = response.get("code", "")
    if resp_code == "AUTHORIZATION_REQUIRED":
        console.print(Panel.fit(
            "[bold red]Atlas authorization expired[/bold red]\n"
            "Your session has expired. Run [bold]adapt atlas-auth-login[/bold] to re-authorize.",
            border_style="red",
        ))
        raise typer.Exit(code=1)
    if response.get("status") != "success" and resp_code:
        console.print(Panel.fit(
            f"[bold red]Atlas error: {resp_code}[/bold red]\n"
            f"{response.get('message', 'Unknown error')}",
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
def book(
    text: str | None = typer.Option(
        None,
        "--nl",
        help='Natural-language flight request (e.g. "Tokyo to Shanghai on 26 September, 2 adults").',
    ),
    seat_policy: str = typer.Option(
        "continue-without-seat",
        "--seat-policy",
        help="Seat fallback policy: continue-without-seat, cancel-order, or accept-similar-seat.",
    ),
) -> None:
    """Book a flight through the Atlas API with interactive checkpoints.

    ADAPT will search Atlas, let you pick an offer, verify the price,
    collect passenger details, create the order, and process payment --
    with your approval at every side-effecting step.
    """
    from datetime import date as _date

    from adapt.agents.booking import BookingAgent
    from adapt.atlas import AtlasClient, AtlasError, AtlasUnavailable
    from adapt.models import BookingStage

    console = fmt.console
    llm = get_llm_client()

    # --- 1. Get natural-language input (reuse search parsing) ------------
    if text is None:
        console.print(Panel.fit(
            "[bold cyan]ADAPT Flight Booking[/bold cyan]\n"
            "[dim]Describe the flight you want to book.[/dim]\n"
            '  [green]"Tokyo to Shanghai on 26 September, 2 adults"[/green]\n'
            '  [green]"NYC to London, October 5, 1 adult"[/green]',
            border_style="cyan",
        ))
        text = typer.prompt("What flight do you want to book?")
    if not text or not text.strip():
        console.print("[red]No flight description provided.[/red]")
        raise typer.Exit(code=1)

    # Parse the request
    with console.status("[bold cyan]Parsing your request...[/bold cyan]"):
        parsed = llm.parse_flight_request(text.strip())

    origin = parsed.get("origin")
    destination = parsed.get("destination")
    depart = parsed.get("depart")
    adults = parsed.get("adults", 1)
    missing = list(parsed.get("missing") or [])

    # Regex safety net: fill gaps the LLM missed
    if missing:
        from adapt.llm.parser import parse_flight_request as _regex_parse

        regex_result = _regex_parse(text.strip())
        if not origin and regex_result.origin:
            origin = regex_result.origin
            missing = [m for m in missing if m != "origin"]
        if not destination and regex_result.destination:
            destination = regex_result.destination
            missing = [m for m in missing if m != "destination"]
        if not depart and regex_result.depart:
            depart = regex_result.depart.isoformat()
            missing = [m for m in missing if m != "depart"]

    # Re-prompt for anything missing
    from adapt.llm.parser import _resolve_airport as _resolve

    for fld in missing:
        if fld == "origin":
            raw = typer.prompt("Departing from (city or airport code)").strip()
            origin = _resolve(raw) or raw.upper()
        elif fld == "destination":
            raw = typer.prompt("Flying to (city or airport code)").strip()
            destination = _resolve(raw) or raw.upper()
        elif fld == "depart":
            raw = typer.prompt("Departure date (e.g. 26 September, 2026-09-26)").strip()
            from adapt.llm.parser import parse_flight_request as _regex_parse
            parsed_dt = _regex_parse(f"on {raw}").depart
            if parsed_dt is None:
                console.print(f"[red]Could not parse date '{raw}'.[/red]")
                raise typer.Exit(code=1)
            depart = parsed_dt.isoformat()

    if not (origin and destination and depart):
        console.print("[red]Cannot book without origin, destination, and departure date.[/red]")
        raise typer.Exit(code=1)

    # --- 2. Initialise the booking agent ---------------------------------
    try:
        agent = BookingAgent()
    except AtlasUnavailable as exc:
        console.print(Panel.fit(
            f"[bold red]Atlas CLI unavailable[/bold red]\n{exc}",
            border_style="red",
        ))
        raise typer.Exit(code=1)

    # --- 3. Search -------------------------------------------------------
    with console.status(
        f"[bold cyan]Searching Atlas for {origin} -> {destination} on {depart}...[/bold cyan]"
    ):
        try:
            offers, ticketing_available = agent.search(
                origin=origin.upper(),
                destination=destination.upper(),
                depart=depart,
                adults=adults,
            )
        except (AtlasError, AtlasUnavailable) as exc:
            console.print(Panel.fit(
                f"[bold red]Atlas search failed[/bold red]\n{exc}",
                border_style="red",
            ))
            raise typer.Exit(code=1)

    if not offers:
        console.print(Panel.fit(
            f"[yellow]No offers found for {origin} -> {destination} on {depart}.[/yellow]\n"
            "Try a different date or nearby airport.",
            border_style="yellow",
        ))
        raise typer.Exit(code=0)

    fmt.print_atlas_offers(
        origin.upper(), destination.upper(), depart, offers,
        ticketing_available=ticketing_available,
    )

    if not ticketing_available:
        console.print(
            "\n[red]Ticketing is not active on this Atlas account.[/red]\n"
            "You can search and compare, but booking requires ticketing activation.\n"
            "Run [bold]adapt atlas-auth-status[/bold] to check, or complete activation "
            "in the ATRIP workspace."
        )
        raise typer.Exit(code=1)

    # Filter bookable offers
    bookable = [o for o in offers if not o.is_reference_only]
    if not bookable:
        console.print(
            "\n[yellow]All offers are compare-only -- none can be booked.[/yellow]\n"
            "Ticketing activation may be required."
        )
        raise typer.Exit(code=1)

    # --- 4. User picks an offer ------------------------------------------
    console.print(f"\n[bold]Bookable offers:[/bold] {len(bookable)}")
    if len(bookable) == 1:
        selected = bookable[0]
        console.print(f"Only one bookable offer: [bold]{selected.legs_summary()}[/bold]")
    else:
        idx = typer.prompt(
            f"Which offer to book? (1-{len(bookable)})",
            type=int,
            default=1,
        )
        if idx < 1 or idx > len(bookable):
            console.print("[red]Invalid selection.[/red]")
            raise typer.Exit(code=1)
        selected = bookable[idx - 1]

    console.print(f"\nSelected: [bold]{selected.legs_summary()}[/bold] "
                  f"({selected.total_price:.2f} {selected.currency})")

    # --- 5. Verify -------------------------------------------------------
    with console.status("[bold cyan]Verifying offer price...[/bold cyan]"):
        verify_result = agent.verify(selected)

    fmt.print_verification_result(verify_result)

    if verify_result.stage == BookingStage.FAILED:
        raise typer.Exit(code=1)

    # Handle price increase checkpoint
    if verify_result.price_change == "increased":
        console.print(
            f"\n[bold red]Price increased![/bold red] "
            f"Previous: {verify_result.previous_price:.2f} -> "
            f"New: {verify_result.current_price:.2f} {verify_result.currency}"
        )
        accept = typer.confirm("Do you accept the new price?", default=False)
        if not accept:
            console.print("[yellow]Booking cancelled.[/yellow]")
            raise typer.Exit(code=0)
        with console.status("[bold cyan]Confirming new price...[/bold cyan]"):
            confirm_result = agent.confirm_increased_price(verify_result.booking_id)
        if confirm_result.stage == BookingStage.FAILED:
            fmt.print_booking_result(confirm_result)
            raise typer.Exit(code=1)

    # --- 6. Collect passenger details ------------------------------------
    travelers = verify_result.raw_data.get("travelers", [])
    passenger_details: list[dict[str, str]] = []

    console.print(Panel.fit(
        "[bold cyan]Passenger Details[/bold cyan]\n"
        "[dim]Names should be UPPERCASE FAMILY/GIVEN (e.g. CARTER/JOHN).[/dim]",
        border_style="cyan",
    ))

    for i, traveler in enumerate(travelers, start=1):
        ptype = traveler.get("passenger_type", "adult")
        tid = traveler.get("traveler_id", "")
        console.print(f"\n[bold]Passenger {i}[/bold] ({ptype}, ID: {tid})")
        name = typer.prompt("  Full name (FAMILY/GIVEN)").strip().upper()
        gender = typer.prompt("  Gender (M/F)", default="M").strip().upper()
        birthday = typer.prompt("  Birthday (YYYY-MM-DD)").strip()
        nationality = typer.prompt("  Nationality (2-letter, e.g. US, JP)").strip().upper()

        # Document (optional for now)
        doc_type = typer.prompt("  Document type (PP=passport, leave empty to skip)", default="").strip()
        doc = None
        if doc_type:
            doc_number = typer.prompt("  Document number").strip()
            doc_country = typer.prompt("  Issuing country (2-letter)").strip().upper()
            doc_expires = typer.prompt("  Expiry date (YYYY-MM-DD)").strip()
            doc = {
                "type": doc_type,
                "number": doc_number,
                "issuing_country": doc_country,
                "expires": doc_expires,
            }

        passenger_details.append({
            "name": name,
            "gender": gender,
            "birthday": birthday,
            "nationality": nationality,
            "document": doc,
        })

    # Contact info
    console.print("\n[bold]Contact Information[/bold]")
    contact_name = typer.prompt("  Contact name (FAMILY/GIVEN)").strip().upper()
    contact_email = typer.prompt("  Email (optional)", default="").strip()
    contact_mobile = typer.prompt("  Mobile (optional, e.g. 001-5551234567)", default="").strip()
    contact = {"name": contact_name}
    if contact_email:
        contact["email"] = contact_email
    if contact_mobile:
        contact["mobile"] = contact_mobile

    # --- 7. Create order -------------------------------------------------
    with console.status("[bold cyan]Creating order...[/bold cyan]"):
        order_result = agent.create_order(
            verify_result,
            passenger_details,
            contact,
            seat_policy=seat_policy,
        )

    if order_result.stage == BookingStage.COLLECTING_PASSENGERS:
        console.print(Panel.fit(
            f"[yellow]Passenger info issue[/yellow]\n"
            f"Code: {order_result.error_code}\n"
            f"{order_result.error_message}",
            border_style="yellow",
        ))
        console.print("Please re-run and correct the passenger details.")
        raise typer.Exit(code=1)

    if order_result.stage == BookingStage.FAILED:
        fmt.print_booking_result(order_result)
        raise typer.Exit(code=1)

    # --- 8. Payment checkpoint -------------------------------------------
    if order_result.stage == BookingStage.AWAITING_PAYMENT:
        fmt.print_payment_summary(order_result)
        approve = typer.confirm("\nApprove this payment?", default=False)
        if not approve:
            console.print("[yellow]Payment cancelled. Order was created but not paid.[/yellow]")
            raise typer.Exit(code=0)

        with console.status("[bold cyan]Processing payment...[/bold cyan]"):
            pay_result = agent.pay(order_result)

        fmt.print_booking_result(pay_result)
    else:
        console.print(f"\n[yellow]Unexpected stage: {order_result.stage.value}[/yellow]")
        fmt.print_booking_result(order_result)


@app.command()
def harvest(
    pages: int = typer.Option(5, "--pages", help="Pages to fetch. Each page = 1 API call, <=100 flights."),
    page_size: int = typer.Option(100, "--page-size", help="Flights per page (free plan caps at 100)."),
) -> None:
    """Pull real flights from AviationStack into the local database.

    Each page costs one API call from a ~100-call monthly quota and returns up to
    100 flights, so `--pages 10` buys roughly 1,000 real flights for a tenth of
    the month's budget. Harvested flights are permanent - query them afterwards
    with `adapt flights` at no further API cost.
    """
    if not aviationstack_source.is_available():
        fmt.console.print("[red]AVIATIONSTACK_API_KEY is not set - nothing to harvest.[/red]")
        raise typer.Exit(1)

    fmt.console.print(f"Harvesting up to {pages} page(s) x {page_size} flights...")

    def progress(page: int, added: int, running_total: int) -> None:
        fmt.console.print(f"  page {page}: +{added} flights (stored {running_total} so far)")

    result = aviationstack_source.harvest(pages=pages, page_size=page_size, on_page=progress)

    fmt.console.print(
        f"\n[green]Stored {result['stored']} flights[/green] using "
        f"{result['api_calls']} API call(s). Local DB now holds {result['total_in_db']} flights."
    )
    if result["error"]:
        fmt.console.print(f"[yellow]Stopped early: {result['error']}[/yellow]")


@app.command()
def db_status() -> None:
    """Show what's in the local harvested flight database."""
    info = flight_store.stats()
    fmt.console.print(f"Database  : {info['path']}")
    if not info["exists"] or not info["flights"]:
        fmt.console.print("[yellow]Empty. Populate it with:  adapt harvest --pages 5[/yellow]")
        return

    fmt.console.print(f"Flights   : {info['flights']}  ({info['size_bytes'] / 1024:.0f} KB)")
    fmt.console.print(f"Routes    : {info['routes']} distinct, {info['airports']} airports")
    fmt.console.print(f"Disrupted : {info['disrupted']}")
    if info["harvested_age_seconds"] is not None:
        fmt.console.print(f"Last pull : {info['harvested_age_seconds'] / 3600:.1f}h ago")
    for status, n in sorted(info["by_status"].items(), key=lambda kv: -kv[1]):
        fmt.console.print(f"  {status}: {n}")


@app.command()
def db_clear() -> None:
    """Delete every harvested flight. This data cost API quota - it is not recoverable for free."""
    removed = flight_store.clear()
    fmt.console.print(f"Removed {removed} harvested flight(s) from the local DB.")


@app.command()
def cache_status() -> None:
    """Show what's in the local API cache (the store that saves live-API quota)."""
    info = http_cache.stats()
    fmt.console.print(f"Cache file : {info['path']}")
    if not info["exists"] or not info["entries"]:
        fmt.console.print("[yellow]Empty - every lookup will spend a live API call.[/yellow]")
        return

    fmt.console.print(f"Entries    : {info['entries']}  ({info['size_bytes'] / 1024:.1f} KB)")
    fmt.console.print(f"TTL        : {info['ttl_seconds'] / 3600:.1f}h")
    fmt.console.print(f"Offline    : {'ON - no live calls will be made' if info['offline'] else 'off'}")
    for source, detail in sorted(info["sources"].items()):
        fmt.console.print(
            f"  {source}: {detail['entries']} entries, "
            f"newest {detail['newest_age_seconds'] / 60:.0f}min old, "
            f"oldest {detail['oldest_age_seconds'] / 3600:.1f}h old"
        )


@app.command()
def cache_clear(
    source: str = typer.Option(None, "--source", help="Clear one source only, e.g. aviationstack."),
) -> None:
    """Delete cached API responses, forcing the next lookup to spend a live call."""
    removed = http_cache.clear(source)
    scope = source or "all sources"
    fmt.console.print(f"Removed {removed} cached entr{'y' if removed == 1 else 'ies'} ({scope}).")


@app.command()
def flights(
    source: str = typer.Option(
        "auto",
        "--source",
        help="auto (local DB, then live, then mock) | local | live | mock.",
    ),
    limit: int = typer.Option(25, "--limit", help="How many flights to show."),
    origin: str = typer.Option(None, "--origin", help="Filter by origin airport (local DB only)."),
    destination: str = typer.Option(
        None, "--destination", help="Filter by destination airport (local DB only)."
    ),
    disrupted: bool = typer.Option(
        False, "--disrupted", help="Only delayed/cancelled/diverted flights (local DB only)."
    ),
) -> None:
    """List flights from the local harvested database, the live API, or mock data."""
    source = source.lower()
    if source not in {"auto", "local", "live", "mock"}:
        fmt.console.print(f"[red]Unknown --source '{source}'. Use auto, local, live or mock.[/red]")
        raise typer.Exit(1)

    # Local first under `auto`: it is free, already paid for, and usually far
    # larger than a single 100-row live page.
    if source in {"auto", "local"}:
        rows = flight_store.load(
            limit=limit, origin=origin, destination=destination, disrupted_only=disrupted
        )
        if rows:
            total = flight_store.count()
            fmt.print_flight_table(
                rows, title=f"Local flight DB - showing {len(rows)} of {total} harvested"
            )
            return
        if source == "local":
            fmt.console.print(
                "[yellow]Local flight DB is empty. Populate it with:  adapt harvest --pages 5[/yellow]"
            )
            return

    if source == "mock":
        fmt.print_flight_table(get_flight_db(), title="Mock schedule (offline demo data)")
        return

    live = source in {"auto", "live"}
    if live and aviationstack_source.is_available():
        rows = aviationstack_source.list_live_flights(limit=limit)
        if rows:
            age = aviationstack_source.last_age_seconds()
            freshness = "live" if age < 60 else f"cached, {age / 60:.0f}min old"
            fmt.print_flight_table(
                rows, title=f"AviationStack flights - {freshness} ({len(rows)})"
            )
            if aviationstack_source.last_error():
                fmt.console.print(f"[yellow]{aviationstack_source.last_error()}[/yellow]")
            return
        # Say *why* before falling back. A silent swap to mock rows is how a dead
        # API key or an exhausted quota goes unnoticed for weeks.
        fmt.console.print(
            f"[yellow]Live flight data unavailable: {aviationstack_source.last_error()}.[/yellow]"
        )
    fmt.print_flight_table(get_flight_db(), title="Mock schedule (offline demo data)")


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
