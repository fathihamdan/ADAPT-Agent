"""OpenRouter-backed LLM client. Only imported/instantiated when OPENROUTER_API_KEY is set.

OpenRouter exposes an OpenAI-compatible chat-completions endpoint in front of many
models (including Claude, GPT, Llama, etc), so this needs no extra SDK dependency —
just a plain HTTPS POST.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import date
from typing import Any

from adapt.llm.base import LLMClient

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = os.environ.get("ADAPT_MODEL", "anthropic/claude-sonnet-4.5")

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

_NL_SEARCH_SYSTEM = (
    "You are ADAPT's flight-request parser. Given a free-form English sentence "
    "describing a flight the user wants, extract four fields as JSON:\n"
    '  {"origin": "IATA airport code or null, '
    '"destination": "IATA airport code or null, '
    '"depart": "YYYY-MM-DD or null, '
    '"adults": integer (default 1)}\n'
    "Return ONLY the JSON object — no prose, no markdown fences. If a city name is "
    "given instead of an airport code, pick the primary international airport for that "
    "city (e.g. Tokyo -> NRT, Shanghai -> PVG, London -> LHR). If today's date is "
    "implied ('today', 'tonight', 'this weekend'), use it; if a relative date is "
    "given ('tomorrow', 'next friday'), resolve it against today. Set adults=1 if not "
    "mentioned."
)


class OpenRouterClient(LLMClient):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set.")
        self._model = model or _DEFAULT_MODEL

    @property
    def name(self) -> str:
        return f"OpenRouter ({self._model})"

    def _generate(self, system: str, prompt: str) -> str:
        body = json.dumps(
            {
                "model": self._model,
                "max_tokens": 400,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            _API_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/fathihamdan/ADAPT-Agent",
                "X-Title": "ADAPT-Agent",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenRouter request failed ({exc.code}): {detail}") from exc

        return payload["choices"][0]["message"]["content"].strip()

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

    def parse_flight_request(self, text: str) -> dict[str, Any]:
        """Use the active model to extract origin/destination/date/adults; fall
        back to the shared regex parser on any failure."""
        from adapt.llm.parser import parse_flight_request as _regex_parse

        today_hint = f"Today is {date.today().isoformat()}. "
        try:
            raw = self._generate(_NL_SEARCH_SYSTEM, today_hint + text)
            # Strip any accidental markdown fences the model wraps around the JSON.
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```$", "", cleaned)
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                raise ValueError("model returned non-object JSON")
        except Exception:
            # Any failure — model timeout, bad JSON, network — degrades to regex.
            fallback = _regex_parse(text)
            return {
                "origin": fallback.origin,
                "destination": fallback.destination,
                "depart": fallback.depart.isoformat() if fallback.depart else None,
                "adults": fallback.adults,
                "missing": fallback.missing or [],
                "source": "regex-fallback",
            }

        adults = parsed.get("adults", 1)
        try:
            adults = max(1, min(9, int(adults)))
        except (TypeError, ValueError):
            adults = 1

        missing = [
            field
            for field in ("origin", "destination", "depart")
            if not parsed.get(field)
        ]
        return {
            "origin": (parsed.get("origin") or "").upper() or None,
            "destination": (parsed.get("destination") or "").upper() or None,
            "depart": parsed.get("depart"),
            "adults": adults,
            "missing": missing,
            "source": "llm",
        }
