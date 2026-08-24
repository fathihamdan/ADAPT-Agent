"""Helpers for interacting with the Atlas Flight Booking CLI.

These helpers intentionally keep the integration thin: they shell out to the
`atlas-flight` executable, parse the JSON envelope it emits, and expose a few
small primitives the ADAPT agent can call during booking workflows.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from typing import Any, Sequence


def run_atlas_cli(*args: str) -> dict[str, Any]:
    """Run an Atlas CLI command and return its JSON envelope.

    The Atlas skill contract requires every subcommand to be invoked with
    `--json`, so we keep the shell contract strict and fail loudly when the CLI
    is unavailable or returns a non-JSON payload.
    """

    try:
        completed = subprocess.run(
            ["atlas-flight", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Atlas CLI is not installed or not on PATH. Run `uv tool install --force --python 3.12 atlas-flight-booking==0.3.12`."
        ) from exc

    if completed.returncode != 0:
        error_text = (completed.stderr or completed.stdout or "unknown Atlas CLI error").strip()
        raise RuntimeError(f"Atlas CLI command failed ({completed.returncode}): {error_text}")

    response_text = (completed.stdout or "").strip()
    if not response_text:
        raise RuntimeError("Atlas CLI returned an empty response.")

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Atlas CLI returned invalid JSON: {response_text[:200]}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Atlas CLI returned an unexpected non-dictionary JSON response.")

    return payload


def extract_payload(response: dict[str, Any]) -> dict[str, Any]:
    """Return the opaque "data" payload from an Atlas response envelope."""

    data = response.get("data")
    if isinstance(data, dict):
        return data
    return {}


def build_search_command(
    origin: str,
    destination: str,
    depart: str,
    adults: int,
    *,
    return_date: str | None = None,
    children: int = 0,
    infants: int = 0,
    currency: str | None = None,
    airlines: Sequence[str] | None = None,
) -> str:
    """Render the exact `atlas-flight search` command, including JSON output."""

    args = [
        "atlas-flight",
        "search",
        "--origin",
        origin,
        "--destination",
        destination,
        "--depart",
        depart,
        "--adults",
        str(adults),
    ]
    if return_date:
        args.extend(["--return-date", return_date])
    if children:
        args.extend(["--children", str(children)])
    if infants:
        args.extend(["--infants", str(infants)])
    if currency:
        args.extend(["--currency", currency])
    if airlines:
        for airline in airlines:
            args.extend(["--airline", airline])
    args.append("--json")
    return " ".join(shlex.quote(part) for part in args)


def search_flights(
    origin: str,
    destination: str,
    depart: str,
    adults: int,
    *,
    return_date: str | None = None,
    children: int = 0,
    infants: int = 0,
    currency: str | None = None,
    airlines: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Trigger a new Atlas search."""

    args = [
        "search",
        "--origin",
        origin,
        "--destination",
        destination,
        "--depart",
        depart,
        "--adults",
        str(adults),
    ]
    if return_date:
        args.extend(["--return-date", return_date])
    if children:
        args.extend(["--children", str(children)])
    if infants:
        args.extend(["--infants", str(infants)])
    if currency:
        args.extend(["--currency", currency])
    if airlines:
        for airline in airlines:
            args.extend(["--airline", airline])
    args.append("--json")
    return run_atlas_cli(*args)


def list_offers(search_id: str) -> dict[str, Any]:
    """List flight offers from a retained search result."""

    return run_atlas_cli("offer", "list", "--search-id", search_id, "--json")


def verify_offer(offer_id: str) -> dict[str, Any]:
    """Verify an offer and confirm the current price."""

    return run_atlas_cli("offer", "verify", "--offer-id", offer_id, "--json")


def auth_status() -> dict[str, Any]:
    """Check Atlas authorization and ticketing readiness."""

    return run_atlas_cli("auth", "status", "--json")


def auth_login() -> dict[str, Any]:
    """Start the authorization flow."""

    return run_atlas_cli("auth", "login", "--json")


def auth_poll(timeout: int = 120) -> dict[str, Any]:
    """Poll once for auth completion."""

    return run_atlas_cli("auth", "poll", "--timeout", str(timeout), "--json")


def list_baggage(booking_id: str) -> dict[str, Any]:
    """List ancillaries available for a booking."""

    return run_atlas_cli("booking", "baggage", "list", "--booking-id", booking_id, "--json")


def select_baggage(
    booking_id: str,
    traveler_id: str,
    segment_id: str,
    baggage_id: str,
) -> dict[str, Any]:
    """Select baggage for a booking segment."""

    return run_atlas_cli(
        "booking",
        "baggage",
        "select",
        "--booking-id",
        booking_id,
        "--traveler-id",
        traveler_id,
        "--segment-id",
        segment_id,
        "--baggage-id",
        baggage_id,
        "--json",
    )


def list_seats(booking_id: str) -> dict[str, Any]:
    """List available seats for a booking."""

    return run_atlas_cli("booking", "seat", "list", "--booking-id", booking_id, "--json")


def select_seat(
    booking_id: str,
    traveler_id: str,
    segment_id: str,
    seat_id: str,
) -> dict[str, Any]:
    """Select a seat for a traveler and booking segment."""

    return run_atlas_cli(
        "booking",
        "seat",
        "select",
        "--booking-id",
        booking_id,
        "--traveler-id",
        traveler_id,
        "--segment-id",
        segment_id,
        "--seat-id",
        seat_id,
        "--json",
    )


def build_order_command(
    booking_id: str,
    passengers_source: str,
    *,
    passengers_file: str | None = None,
    seat_policy: str | None = None,
) -> str:
    """Render the exact `atlas-flight order create` command with optional seat policy."""

    if passengers_source not in {"passengers-stdin", "passengers-file"}:
        raise ValueError("passengers_source must be 'passengers-stdin' or 'passengers-file'")

    args = [
        "atlas-flight",
        "order",
        "create",
        "--booking-id",
        booking_id,
        f"--{passengers_source}",
    ]
    if passengers_source == "passengers-file" and passengers_file:
        args.extend(["--passengers-file", passengers_file])
    if seat_policy:
        args.extend(["--seat-policy", seat_policy])
    args.append("--json")
    return " ".join(shlex.quote(part) for part in args)


def create_order(
    booking_id: str,
    passengers_source: str = "passengers-stdin",
    *,
    passengers_file: str | None = None,
    seat_policy: str | None = None,
) -> dict[str, Any]:
    """Create an order using a file or stdin passenger payload."""

    if passengers_source not in {"passengers-stdin", "passengers-file"}:
        raise ValueError("passengers_source must be 'passengers-stdin' or 'passengers-file'")

    args = [
        "order",
        "create",
        "--booking-id",
        booking_id,
        f"--{passengers_source}",
    ]
    if passengers_source == "passengers-file" and passengers_file:
        args.extend(["--passengers-file", passengers_file])
    if seat_policy:
        args.extend(["--seat-policy", seat_policy])
    args.append("--json")
    return run_atlas_cli(*args)


def pay_order(payment_confirmation_id: str) -> dict[str, Any]:
    """Pay for a previously confirmed order."""

    return run_atlas_cli("order", "pay", "--confirmation-id", payment_confirmation_id, "--json")


def order_status(order_no: str) -> dict[str, Any]:
    """Query status for an order or ticketing lifecycle."""

    return run_atlas_cli("order", "status", "--order-no", order_no, "--json")

