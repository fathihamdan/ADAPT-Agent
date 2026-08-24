"""Autonomous Atlas booking agent for ADAPT.

Implements the full search -> verify -> order -> pay -> ticketing workflow
with mandatory user checkpoints before every side-effecting step. The agent
drives the Atlas CLI through `AtlasClient` and surfaces human-readable
summaries at each checkpoint so the user stays in control.

Checkpoints (per the Atlas skill contract):
  1. PRICE INCREASE  - show old vs new total, wait for explicit acceptance.
  2. SEAT FALLBACK   - ask what to do if a selected seat becomes unavailable.
  3. PAYMENT         - present the current masked summary, wait for approval.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from adapt.atlas.client import AtlasClient, AtlasError, AtlasOffer, AtlasUnavailable
from adapt.models import BookingResult, BookingStage


# ---------------------------------------------------------------------------
# Passenger collection helpers
# ---------------------------------------------------------------------------

def _build_passenger_payload(
    travelers: list[dict[str, Any]],
    passenger_details: list[dict[str, str]],
    contact: dict[str, str],
) -> dict[str, Any]:
    """Build the stdin JSON payload for `order create --passengers-stdin`.

    `travelers` comes from the verify response (`data.travelers`) and carries
    `traveler_id` and `passenger_type`. `passenger_details` is the user-provided
    info collected during the interactive flow.
    """
    passengers = []
    for traveler, details in zip(travelers, passenger_details):
        entry: dict[str, Any] = {
            "traveler_id": traveler["traveler_id"],
            "name": details["name"],
            "passenger_type": traveler.get("passenger_type", "adult"),
            "gender": details.get("gender", ""),
            "birthday": details.get("birthday", ""),
            "nationality": details.get("nationality", ""),
        }
        doc = details.get("document")
        if doc:
            entry["document"] = doc
        passengers.append(entry)

    result: dict[str, Any] = {"passengers": passengers}
    if contact:
        result["contact"] = contact
    return result


# ---------------------------------------------------------------------------
# Booking agent
# ---------------------------------------------------------------------------

class BookingAgent:
    """Drives the Atlas booking pipeline with user checkpoints.

    Usage::

        agent = BookingAgent()
        result = agent.search(origin="NRT", destination="PVG", depart="2026-09-26", adults=2)
        # ... user picks an offer ...
        result = agent.verify_and_book(selected_offer, passenger_details, contact)
    """

    def __init__(self, client: AtlasClient | None = None) -> None:
        self._client = client or AtlasClient()

    # -- step 1: search ---------------------------------------------------

    def search(
        self,
        *,
        origin: str,
        destination: str,
        depart: str,
        adults: int = 1,
    ) -> tuple[list[AtlasOffer], bool]:
        """Search Atlas and return (offers, ticketing_available).

        Raises AtlasUnavailable or AtlasError on failure.
        """
        auth = self._client.auth_status()
        ticketing_available = bool(
            auth.get("code") == "AUTHORIZED"
            and (auth.get("data") or {}).get("ticketing_available")
        )

        depart_dt = datetime.strptime(depart, "%Y-%m-%d")
        offers = self._client.search(
            origin=origin,
            destination=destination,
            depart=depart_dt,
            adults=adults,
        )
        return offers, ticketing_available

    # -- step 2: verify ---------------------------------------------------

    def verify(self, offer: AtlasOffer) -> BookingResult:
        """Verify an offer's current price.

        Returns a BookingResult with stage=VERIFYING (success) or
        stage=FAILED. The caller should check `price_change` and
        `booking_id` before proceeding to order creation.
        """
        try:
            envelope = self._client.verify(offer.offer_id)
        except AtlasError as exc:
            return BookingResult(
                stage=BookingStage.FAILED,
                offer_id=offer.offer_id,
                error_code=exc.code,
                error_message=exc.message,
            )

        code = envelope.get("code", "")
        data = envelope.get("data", {}) or {}

        if code == "OFFER_EXPIRED" or code == "FLIGHT_UNAVAILABLE":
            return BookingResult(
                stage=BookingStage.FAILED,
                offer_id=offer.offer_id,
                error_code=code,
                error_message=data.get("message", "Offer expired or flight unavailable"),
            )

        booking_id = data.get("booking_id", "")
        price_change = data.get("price_change", "unchanged")
        previous_price = data.get("previous_price")
        current_price = data.get("current_price")

        return BookingResult(
            stage=BookingStage.VERIFYING,
            offer_id=offer.offer_id,
            booking_id=booking_id,
            total_price=float(current_price or offer.total_price),
            currency=data.get("currency", offer.currency),
            price_change=price_change,
            previous_price=float(previous_price) if previous_price else None,
            current_price=float(current_price) if current_price else None,
            raw_data=data,
        )

    def confirm_increased_price(self, booking_id: str) -> BookingResult:
        """Confirm an increased price after user approval."""
        try:
            envelope = self._client.confirm_price(booking_id)
        except AtlasError as exc:
            return BookingResult(
                stage=BookingStage.FAILED,
                booking_id=booking_id,
                error_code=exc.code,
                error_message=exc.message,
            )

        code = envelope.get("code", "")
        if code == "PRICE_CONFIRMED":
            return BookingResult(
                stage=BookingStage.VERIFYING,
                booking_id=booking_id,
                raw_data=envelope.get("data", {}),
            )
        return BookingResult(
            stage=BookingStage.FAILED,
            booking_id=booking_id,
            error_code=code,
            error_message=envelope.get("message", "Price confirmation failed"),
        )

    # -- step 3: collect passengers & create order -------------------------

    def create_order(
        self,
        verify_result: BookingResult,
        passenger_details: list[dict[str, str]],
        contact: dict[str, str],
        *,
        seat_policy: str = "continue-without-seat",
    ) -> BookingResult:
        """Create the order using verified booking + passenger details.

        Returns BookingResult with stage=AWAITING_PAYMENT on success,
        or FAILED on error.
        """
        data = verify_result.raw_data
        travelers = data.get("travelers", [])
        if not travelers:
            return BookingResult(
                stage=BookingStage.FAILED,
                booking_id=verify_result.booking_id,
                error_code="NO_TRAVELERS",
                error_message="No traveler records from verification",
            )

        payload = _build_passenger_payload(travelers, passenger_details, contact)

        try:
            envelope = self._client.create_order(
                verify_result.booking_id,
                payload,
                seat_policy=seat_policy,
            )
        except AtlasError as exc:
            return BookingResult(
                stage=BookingStage.FAILED,
                booking_id=verify_result.booking_id,
                error_code=exc.code,
                error_message=exc.message,
            )

        code = envelope.get("code", "")
        resp_data = envelope.get("data", {}) or {}

        if code == "PAYMENT_CONFIRMATION_REQUIRED":
            return BookingResult(
                stage=BookingStage.AWAITING_PAYMENT,
                booking_id=verify_result.booking_id,
                payment_confirmation_id=resp_data.get("payment_confirmation_id", ""),
                total_price=float(resp_data.get("total_price", 0.0)),
                currency=resp_data.get("currency", "USD"),
                price_change=resp_data.get("price_change"),
                previous_price=(
                    float(resp_data["previous_price"]) if resp_data.get("previous_price") else None
                ),
                current_price=(
                    float(resp_data["current_price"]) if resp_data.get("current_price") else None
                ),
                order_url=resp_data.get("order_url"),
                raw_data=resp_data,
            )

        if code in ("PASSENGER_INFO_REQUIRED", "PASSENGER_INFO_INVALID", "CONTACT_INFO_INVALID"):
            return BookingResult(
                stage=BookingStage.COLLECTING_PASSENGERS,
                booking_id=verify_result.booking_id,
                error_code=code,
                error_message=resp_data.get("message", ""),
                raw_data=resp_data,
            )

        if code in ("ORDER_CREATION_UNKNOWN", "DUPLICATE_BOOKING_SUSPECTED"):
            return BookingResult(
                stage=BookingStage.FAILED,
                booking_id=verify_result.booking_id,
                error_code=code,
                error_message=resp_data.get("message", "Order creation uncertain"),
                order_url=resp_data.get("order_url"),
            )

        return BookingResult(
            stage=BookingStage.FAILED,
            booking_id=verify_result.booking_id,
            error_code=code,
            error_message=envelope.get("message", "Order creation failed"),
        )

    # -- step 4: pay ------------------------------------------------------

    def pay(self, booking_result: BookingResult) -> BookingResult:
        """Pay for the order using the single-use confirmation ID.

        Must be called after a successful AWAITING_PAYMENT result.
        """
        try:
            envelope = self._client.pay(booking_result.payment_confirmation_id)
        except AtlasError as exc:
            return BookingResult(
                stage=BookingStage.FAILED,
                booking_id=booking_result.booking_id,
                error_code=exc.code,
                error_message=exc.message,
            )

        code = envelope.get("code", "")
        data = envelope.get("data", {}) or {}

        if code == "TICKETED":
            return BookingResult(
                stage=BookingStage.TICKETED,
                booking_id=booking_result.booking_id,
                order_no=data.get("order_no", ""),
                total_price=booking_result.total_price,
                currency=booking_result.currency,
                order_url=data.get("order_url"),
                raw_data=data,
            )

        if code == "TICKETING_PENDING":
            return BookingResult(
                stage=BookingStage.TICKETING_PENDING,
                booking_id=booking_result.booking_id,
                order_no=data.get("order_no", ""),
                total_price=booking_result.total_price,
                currency=booking_result.currency,
                order_url=data.get("order_url"),
                raw_data=data,
            )

        if code == "PAYMENT_BALANCE_CHECK_REQUIRED":
            return BookingResult(
                stage=BookingStage.FAILED,
                booking_id=booking_result.booking_id,
                error_code=code,
                error_message="Payment could not be confirmed. ATRIP balance may be insufficient.",
                order_url=data.get("order_url"),
                raw_data=data,
            )

        if code in ("PAYMENT_STATUS_UNKNOWN", "PAYMENT_PROCESSING"):
            order_no = data.get("order_no", "")
            if order_no:
                return self._check_order_status(order_no, booking_result)
            return BookingResult(
                stage=BookingStage.TICKETING_PENDING,
                booking_id=booking_result.booking_id,
                order_no=order_no,
                error_code=code,
                error_message="Payment status uncertain; check later.",
                order_url=data.get("order_url"),
                raw_data=data,
            )

        return BookingResult(
            stage=BookingStage.FAILED,
            booking_id=booking_result.booking_id,
            error_code=code,
            error_message=envelope.get("message", "Payment failed"),
            order_url=data.get("order_url"),
        )

    # -- step 5: status query ---------------------------------------------

    def _check_order_status(
        self, order_no: str, context: BookingResult
    ) -> BookingResult:
        """Query order status as a fallback after uncertain payment."""
        try:
            envelope = self._client.order_status(order_no)
        except AtlasError:
            return BookingResult(
                stage=BookingStage.TICKETING_PENDING,
                booking_id=context.booking_id,
                order_no=order_no,
                error_code="STATUS_QUERY_FAILED",
                error_message="Could not query order status",
            )

        code = envelope.get("code", "")
        data = envelope.get("data", {}) or {}

        if code == "TICKETED":
            return BookingResult(
                stage=BookingStage.TICKETED,
                booking_id=context.booking_id,
                order_no=order_no,
                order_url=data.get("order_url"),
                raw_data=data,
            )
        if code == "TICKETING_PENDING":
            return BookingResult(
                stage=BookingStage.TICKETING_PENDING,
                booking_id=context.booking_id,
                order_no=order_no,
                order_url=data.get("order_url"),
                raw_data=data,
            )
        return BookingResult(
            stage=BookingStage.TICKETING_PENDING,
            booking_id=context.booking_id,
            order_no=order_no,
            error_code=code,
            raw_data=data,
        )

    def check_order_status(self, order_no: str) -> dict[str, Any]:
        """Public wrapper to query order status on demand."""
        return self._client.order_status(order_no)

    # -- optional services ------------------------------------------------

    def list_baggage(self, booking_id: str) -> dict[str, Any]:
        """List available baggage for the booking."""
        try:
            return self._client.list_baggage(booking_id)
        except AtlasError as exc:
            return {"code": exc.code, "message": exc.message, "data": {}}

    def list_seats(self, booking_id: str) -> dict[str, Any]:
        """List available seats for the booking."""
        try:
            return self._client.list_seats(booking_id)
        except AtlasError as exc:
            return {"code": exc.code, "message": exc.message, "data": {}}
