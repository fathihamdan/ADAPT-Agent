"""Anthropic-backed LLM client. Only imported/instantiated when ANTHROPIC_API_KEY is set."""

from __future__ import annotations

import os
from typing import Any

from adapt.llm.base import LLMClient
from adapt.llm.prompts import EXPLAINER_SYSTEM, REROUTE_SYSTEM, RISK_SYSTEM

_DEFAULT_MODEL = os.environ.get("ADAPT_MODEL", "claude-sonnet-5")


class AnthropicClient(LLMClient):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "The 'anthropic' package is required for AnthropicClient. Install it with "
                "`pip install anthropic`."
            ) from exc

        self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self._model = model or _DEFAULT_MODEL
        self._anthropic = anthropic

    @property
    def name(self) -> str:
        return f"Anthropic ({self._model})"

    def _generate(self, system: str, prompt: str) -> str:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=250,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except self._anthropic.APIError as exc:
            raise RuntimeError(f"Anthropic request failed: {exc.message}") from exc
        return "".join(block.text for block in response.content if block.type == "text").strip()

    def explain_disruption(self, context: dict[str, Any]) -> str:
        prompt = (
            f"Flight: {context['flight_no']} ({context['origin']} -> {context['destination']})\n"
            f"Status: {context['status']}\n"
            f"Delay: {context.get('delay_minutes', 0)} minutes\n"
            f"Cause code: {context.get('cause', 'NONE')}\n"
            f"Raw ops note: {context.get('raw_ops_note', '(none)')}\n\n"
            "Explain this disruption to the traveler."
        )
        return self._generate(EXPLAINER_SYSTEM, prompt)

    def describe_risk(self, context: dict[str, Any]) -> str:
        prompt = (
            f"Connection airport: {context['connection_airport']}\n"
            f"Available connection time: {round(context['available_minutes'])} minutes\n"
            f"Required connection time: {round(context['required_minutes'])} minutes\n"
            f"Same terminal: {context.get('same_terminal', True)}\n"
            f"Computed risk level: {context['risk_level']}\n"
            f"Computed probability of missing connection: {round(context['probability_missed'] * 100)}%\n\n"
            "Summarize this risk assessment for the traveler."
        )
        return self._generate(RISK_SYSTEM, prompt)

    def recommend_reroute(self, context: dict[str, Any]) -> str:
        options = context.get("options", [])
        options_text = "\n".join(
            f"{i}. {opt['legs_summary']} -> arrives {opt['arrival']} "
            f"({opt['delay_vs_original']:+d} min vs original, {opt['connections']} connection(s))"
            for i, opt in enumerate(options, start=1)
        ) or "(none found)"
        prompt = (
            f"Destination: {context.get('destination', 'unknown')}\n"
            f"Reason for rerouting: {context.get('reason', 'unknown')}\n"
            f"Ranked alternative options:\n{options_text}\n\n"
            "Recommend the best option and briefly justify it."
        )
        return self._generate(REROUTE_SYSTEM, prompt)
