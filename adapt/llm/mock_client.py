"""Offline LLM backend: no API key required.

Produces plain-English output from structured facts using a small jargon glossary and
templates. It's deliberately simple — deterministic and dependency-free — so the CLI is
fully demoable before any real model is wired in. Swap in AnthropicClient for genuinely
generative explanations once you have a key.
"""

from __future__ import annotations

from typing import Any

from adapt.llm.base import LLMClient

# Airline-ops jargon -> plain English. Longest keys first so multi-word codes match
# before their substrings.
_GLOSSARY = {
    "GROUND STOP": "a temporary halt on departures",
    "GS PGM": "a ground stop program",
    "LLWS": "low-level wind shear",
    "THUNDERSTORM CELLS": "thunderstorms",
    "EDCT": "a new FAA-assigned departure time",
    "RWY CLSD": "the runway being closed",
    "MX AOG": "a mechanical issue grounding the aircraft",
    "AOG": "aircraft grounded for maintenance",
    "NO SPARE ACFT AVBL": "no spare aircraft available to swap in",
    "TMU VOL/CAPACITY CONSTRAINT": "air traffic control limiting how many planes can land",
    "ARR RATE REDUCED": "a reduced landing rate",
    "ATC": "air traffic control",
    "CNX": "cancelled",
    "DLY": "delay",
    "REF FAA ADVZY": "per an FAA advisory",
    "TECH LOG": "the maintenance log",
    "PARTS ETA": "replacement parts are expected in",
}

_CAUSE_PLAIN = {
    "WEATHER": "weather conditions",
    "ATC": "an air traffic control restriction",
    "MECHANICAL": "a mechanical issue with the aircraft",
    "CREW": "a crew scheduling issue",
    "SECURITY": "a security matter",
    "LATE_INBOUND_AIRCRAFT": "the incoming aircraft arriving late",
    "NONE": "no disruption",
}


def _plain_from_ops_note(raw_note: str) -> str:
    hits: list[str] = []
    for code, meaning in _GLOSSARY.items():
        if code in raw_note:
            hits.append(meaning)
    if not hits:
        return ""
    # De-dupe while preserving order.
    seen: set[str] = set()
    ordered = [h for h in hits if not (h in seen or seen.add(h))]
    return ", ".join(ordered)


class MockLLMClient(LLMClient):
    @property
    def name(self) -> str:
        return "offline/rule-based (no API key set)"

    def explain_disruption(self, context: dict[str, Any]) -> str:
        flight_no = context["flight_no"]
        origin = context["origin"]
        destination = context["destination"]
        status = context["status"]
        delay_minutes = context.get("delay_minutes", 0)
        cause = context.get("cause", "NONE")
        raw_note = context.get("raw_ops_note", "")

        cause_plain = _CAUSE_PLAIN.get(cause, cause.lower())
        detail = _plain_from_ops_note(raw_note)

        if status == "CANCELLED":
            base = (
                f"Flight {flight_no} ({origin} to {destination}) has been cancelled due to "
                f"{cause_plain}."
            )
        elif status == "DELAYED":
            base = (
                f"Flight {flight_no} ({origin} to {destination}) is delayed about "
                f"{delay_minutes} minutes because of {cause_plain}."
            )
        else:
            base = f"Flight {flight_no} ({origin} to {destination}) is currently on time."

        if detail:
            base += f" In plain terms: this involves {detail}."

        if status == "CANCELLED":
            base += " The airline will need to rebook you on a different flight."
        elif status == "DELAYED" and delay_minutes >= 60:
            base += " This is a significant delay — if you have a connection, it's worth checking your risk of missing it."

        return base

    def describe_risk(self, context: dict[str, Any]) -> str:
        available = context["available_minutes"]
        required = context["required_minutes"]
        probability = context["probability_missed"]
        level = context["risk_level"]
        airport = context["connection_airport"]
        same_terminal = context.get("same_terminal", True)

        pct = round(probability * 100)
        margin = round(available - required)

        terminal_note = (
            "you're staying in the same terminal" if same_terminal else "you'll need to change terminals"
        )

        if level == "CRITICAL":
            verdict = (
                f"You are very likely to miss your connection at {airport} — "
                f"there's only {round(available)} minutes between landing and your next departure, "
                f"but you realistically need about {round(required)} ({terminal_note})."
            )
        elif level == "HIGH":
            verdict = (
                f"Your connection at {airport} is at high risk. You'll have roughly "
                f"{round(available)} minutes on the ground against a {round(required)}-minute "
                f"requirement ({terminal_note}) — a margin of only {margin} minutes."
            )
        elif level == "MEDIUM":
            verdict = (
                f"Your connection at {airport} is workable but tight — about {margin} minutes of "
                f"buffer after accounting for {terminal_note}. Head straight to your next gate."
            )
        else:
            verdict = (
                f"Your connection at {airport} looks comfortable, with about {margin} minutes of "
                f"buffer beyond what you need ({terminal_note})."
            )

        return f"{verdict} Estimated probability of missing this connection: {pct}%."

    def recommend_reroute(self, context: dict[str, Any]) -> str:
        options = context.get("options", [])
        destination = context.get("destination", "your destination")
        reason = context.get("reason", "your original connection is at risk")
        atlas_note = context.get("atlas_note")

        if not options:
            return (
                f"No alternative flights to {destination} were found in the schedule. "
                "Recommend contacting the airline's rebooking desk directly."
            )

        best = options[0]
        lines = [
            f"Because {reason}, here are the best alternatives to reach {destination}:",
        ]
        if atlas_note:
            lines.append(f"  (source: {atlas_note})")
        for i, opt in enumerate(options, start=1):
            marker = "Recommended: " if i == 1 else ""
            price_suffix = ""
            if opt.get("price"):
                status = opt.get("price_status") or "reference"
                bookable = opt.get("bookable")
                if bookable and status == "current":
                    price_suffix = f" — {opt['price']} (live, bookable)"
                else:
                    price_suffix = f" — {opt['price']} (reference price — compare only)"
            lines.append(
                f"  {i}. {marker}{opt['legs_summary']} — arrives {opt['arrival']} "
                f"({opt['delay_vs_original']:+d} min vs. original plan, "
                f"{opt['connections']} connection(s)){price_suffix}"
            )
        lines.append(
            f"Best option is flight(s) {best['legs_summary']}, arriving {best['arrival']}, "
            f"which minimizes total delay while keeping the itinerary simple."
        )
        if any(o.get("from_atlas") for o in options):
            lines.append(
                "Offers from Atlas are comparison-only until you verify the live fare and "
                "confirm payment with the booking agent."
            )
        return "\n".join(lines)
