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
    "LOW VIS": "low visibility conditions",
    "DIV K": "a diversion to a different airport",
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
    "UNKNOWN": "a reason not reported in the tracking data",
}


def _primary_detail(raw_note: str) -> str:
    """Single most relevant plain-English phrase for this ops note, not every match.

    Piling on every glossary hit produced a run-on comma list; one well-chosen phrase
    reads far cleaner and is enough to make the raw note feel decoded.
    """
    for code, meaning in _GLOSSARY.items():
        if code in raw_note:
            return meaning
    return ""


_ACTION_CANCELLED = "The airline will rebook the passenger automatically — no action needed from the desk yet."
_ACTION_LONG_DELAY = "That's significant — worth checking the passenger's connection risk if they have one."
_ACTION_SHORT_DELAY = "No action needed — just a short wait."
_ACTION_ON_TIME = "Nothing to do here."
_ACTION_DIVERTED = "The airline will get the passenger to their original destination once conditions allow."


class MockLLMClient(LLMClient):
    @property
    def name(self) -> str:
        return "offline/rule-based (no API key set)"

    def explain_disruption(self, context: dict[str, Any]) -> str:
        """Always the same two-part shape: headline (what + why), then one action line.

        Keeping the structure fixed makes every explanation scannable at a glance,
        rather than varying in length and shape depending on how much jargon a given
        ops note happened to contain.
        """
        flight_no = context["flight_no"]
        origin = context["origin"]
        destination = context["destination"]
        status = context["status"]
        delay_minutes = context.get("delay_minutes", 0)
        cause = context.get("cause", "NONE")
        raw_note = context.get("raw_ops_note", "")

        cause_plain = _CAUSE_PLAIN.get(cause, cause.lower())
        detail = _primary_detail(raw_note)

        if status == "CANCELLED":
            headline = f"Flight {flight_no} ({origin} → {destination}) was cancelled because of {cause_plain}."
            action = _ACTION_CANCELLED
        elif status == "DELAYED":
            headline = f"Flight {flight_no} ({origin} → {destination}) is delayed {delay_minutes} min because of {cause_plain}."
            action = _ACTION_LONG_DELAY if delay_minutes >= 60 else _ACTION_SHORT_DELAY
        elif status == "DIVERTED":
            headline = f"Flight {flight_no} ({origin} → {destination}) was diverted to a different airport because of {cause_plain}."
            action = _ACTION_DIVERTED
        else:
            headline = f"Flight {flight_no} ({origin} → {destination}) is on time."
            action = _ACTION_ON_TIME

        if detail:
            headline += f" In short, {detail}."

        return f"{headline} {action}"

    def describe_risk(self, context: dict[str, Any]) -> str:
        available = context["available_minutes"]
        required = context["required_minutes"]
        probability = context["probability_missed"]
        level = context["risk_level"]
        airport = context["connection_airport"]
        same_terminal = context.get("same_terminal", True)

        pct = round(probability * 100)
        margin = round(available - required)

        terminal_note = "no terminal change" if same_terminal else "a terminal change"

        if level == "CRITICAL":
            verdict = (
                f"The passenger is very likely to miss their connection at {airport} — "
                f"there's only {round(available)} minutes between landing and their next departure, "
                f"but they realistically need about {round(required)} ({terminal_note})."
            )
        elif level == "HIGH":
            verdict = (
                f"The passenger's connection at {airport} is at high risk. They'll have roughly "
                f"{round(available)} minutes on the ground against a {round(required)}-minute "
                f"requirement ({terminal_note}) — a margin of only {margin} minutes."
            )
        elif level == "MEDIUM":
            verdict = (
                f"The passenger's connection at {airport} is workable but tight — about {margin} minutes "
                f"of buffer after accounting for {terminal_note}. Worth a proactive check-in."
            )
        else:
            verdict = (
                f"The passenger's connection at {airport} looks comfortable, with about {margin} minutes "
                f"of buffer beyond what they need ({terminal_note})."
            )

        return f"{verdict} Estimated probability of missing this connection: {pct}%."

    def recommend_reroute(self, context: dict[str, Any]) -> str:
        options = context.get("options", [])
        destination = context.get("destination", "the passenger's destination")
        reason = context.get("reason", "the passenger's original connection is at risk")
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
            if opt.get("layovers"):
                lines.append(f"     transit: {', '.join(opt['layovers'])}")
            if opt.get("self_transfer"):
                lines.append(
                    "     separate tickets — the passenger self-transfers, so a misconnect "
                    "is not protected by either airline"
                )
        rationale = (
            "which minimizes total delay while keeping the itinerary simple"
            if not best.get("connections")
            else "the earliest arrival available on this route"
        )
        lines.append(
            f"Best option is flight(s) {best['legs_summary']}, arriving {best['arrival']}, "
            f"{rationale}."
        )
        if best.get("self_transfer"):
            lines.append(
                "Note it is a self-transfer built from separate tickets because no single "
                "through-fare exists on this route — quote the transit time to the customer "
                "and book each ticket separately."
            )
        if any(o.get("from_atlas") for o in options):
            lines.append(
                "Offers from Atlas are comparison-only until you verify the live fare and "
                "confirm payment with the booking agent."
            )
        return "\n".join(lines)
