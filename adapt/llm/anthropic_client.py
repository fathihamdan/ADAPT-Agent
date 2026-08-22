"""Anthropic-backed LLM client. Only imported/instantiated when ANTHROPIC_API_KEY is set."""

from __future__ import annotations

import os
from typing import Any

from adapt.llm.base import LLMClient

_DEFAULT_MODEL = os.environ.get("ADAPT_MODEL", "claude-sonnet-5")

_EXPLAINER_SYSTEM = (
    "You are ADAPT, an airline disruption assistant. Translate cryptic airline "
    "operations notes and disruption codes into a short, clear, reassuring explanation "
    "a traveler can understand in a few seconds. 2-4 sentences. No airline jargon."
)

_RISK_SYSTEM = (
    "You are ADAPT, an airline connection-risk assistant. Given a computed connection "
    "risk assessment (already-calculated numbers, do not recompute them), explain the "
    "situation to the traveler in 2-3 plain-English sentences and end with the stated "
    "probability of missing the connection."
)

_REROUTE_SYSTEM = (
    "You are ADAPT, an airline rerouting assistant. Given a ranked list of alternative "
    "flight options (already ranked, do not re-rank), recommend the best one to the "
    "traveler and briefly justify why, then list the other options as backups. Be concise."
)


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

    @property
    def name(self) -> str:
        return f"Anthropic ({self._model})"

    def _generate(self, system: str, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=400,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
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
        return self._generate(_EXPLAINER_SYSTEM, prompt)

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
        return self._generate(_RISK_SYSTEM, prompt)

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
        return self._generate(_REROUTE_SYSTEM, prompt)
