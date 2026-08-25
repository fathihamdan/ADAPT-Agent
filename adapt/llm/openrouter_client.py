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
from adapt.llm.prompts import (
    EXPLAINER_SYSTEM,
    REROUTE_SYSTEM,
    RISK_SYSTEM,
    format_reroute_options,
)

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = os.environ.get("ADAPT_MODEL", "anthropic/claude-sonnet-4.5")


def _extract_error_message(raw_body: str) -> str:
    """Pull the human-readable message out of OpenRouter's error JSON.

    OpenRouter error bodies are a deeply nested object (error.message, plus a
    metadata blob with duplicate previous_errors). Surfacing the whole thing to a
    traveler-facing error is unreadable, so just take the one line that matters.
    """
    try:
        parsed = json.loads(raw_body)
        return str(parsed["error"]["message"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return raw_body[:200]

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
        # 1500 gives headroom for reasoning models (e.g. the free nvidia/nemotron-nano
        # tier) whose hidden chain-of-thought eats into the budget before any visible
        # output - observed anywhere from ~250 to ~380 reasoning tokens for the same
        # prompt across repeated calls. A tighter cap risks truncating the actual
        # answer (finish_reason=length, content=None).
        body = json.dumps(
            {
                "model": self._model,
                "max_tokens": 1500,
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
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenRouter request failed: {_extract_error_message(raw)}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Could not reach OpenRouter: {exc}") from exc

        choice = payload["choices"][0]
        content = choice["message"].get("content")
        if not content:
            # Reasoning models can exhaust the token budget on hidden chain-of-thought
            # before emitting any visible output, leaving content empty/None even
            # though the request itself succeeded.
            raise RuntimeError(
                f"{self._model} returned no usable content (finish_reason="
                f"{choice.get('finish_reason')!r}) - it may have used its entire "
                "token budget on internal reasoning. Try again, or switch models."
            )
        return content.strip()

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
        options_text = format_reroute_options(context.get("options", []))
        prompt = (
            f"Destination: {context.get('destination', 'unknown')}\n"
            f"Reason for rerouting: {context.get('reason', 'unknown')}\n"
            f"Ranked alternative options:\n{options_text}\n\n"
            "Recommend the best option and briefly justify it."
        )
        return self._generate(REROUTE_SYSTEM, prompt)

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
