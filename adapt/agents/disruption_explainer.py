"""Disruption Explainer: turns a flight's raw status/ops data into a plain-English explanation."""

from __future__ import annotations

from adapt.llm.base import LLMClient
from adapt.models import Flight


def explain(flight: Flight, llm: LLMClient) -> str:
    context = {
        "flight_no": flight.flight_no,
        "origin": flight.origin,
        "destination": flight.destination,
        "status": flight.status.value,
        "delay_minutes": flight.delay_minutes,
        "cause": flight.cause.value,
        "raw_ops_note": flight.raw_ops_note,
    }
    return llm.explain_disruption(context)
