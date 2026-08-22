"""Booking workflow helper for disrupted itineraries.

This module translates the Atlas skill guidance into a structured rebooking plan
that the main ADAPT agent can follow when a leg is cancelled or a connection is
high-risk. The plan is deterministic and is built from the CLI contract rather
than from an LLM prompt.
"""

from __future__ import annotations

from typing import Any


def build_rebooking_plan(
    *,
    origin: str,
    destination: str,
    depart: str,
    adults: int = 1,
    reason: str,
    return_date: str | None = None,
    booking_id: str | None = None,
    seat_policy: str = "continue-without-seat",
) -> dict[str, Any]:
    """Create a structured booking plan for a disrupted itinerary.

    The plan follows the Atlas booking workflow and includes the required human
    checkpoints before verifying price, creating the order, and paying.
    """

    steps: list[dict[str, str]] = [
        {
            "stage": "authorization",
            "command": "atlas-flight auth status --json",
            "description": "Check whether Atlas authorization and ticketing readiness are active.",
        },
        {
            "stage": "search",
            "command": (
                f"atlas-flight search --origin {origin} --destination {destination} "
                f"--depart {depart} --adults {adults} --json"
                + (f" --return-date {return_date}" if return_date else "")
            ),
            "description": "Search for replacement flights matching the disrupted itinerary.",
        },
        {
            "stage": "verify",
            "command": "atlas-flight offer verify --offer-id {offer_id} --json",
            "description": "Verify the selected offer and re-check the current price before committing.",
        },
        {
            "stage": "order",
            "command": (
                f"atlas-flight order create --booking-id {booking_id or '{booking_id}'} "
                f"--passengers-stdin --seat-policy {seat_policy} --json"
            ),
            "description": "Create the booking only after the user accepts the verified price and itinerary.",
        },
        {
            "stage": "pay",
            "command": "atlas-flight order pay --confirmation-id {payment_confirmation_id} --json",
            "description": "Approve payment after the final summary and confirmation ID are shown.",
        },
    ]

    return {
        "reason": reason,
        "origin": origin,
        "destination": destination,
        "depart": depart,
        "adults": adults,
        "return_date": return_date,
        "seat_policy": seat_policy,
        "steps": steps,
    }
