"""LLM client interface. Every agent talks to this, never to a specific provider SDK.

Methods take structured context (dicts of already-computed facts) rather than free text,
so the mock backend can produce reliable canned output without needing to parse a prompt,
and a real backend just needs to turn the same facts into a prompt.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMClient(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable label for the active backend, shown in CLI output."""
        raise NotImplementedError

    @abstractmethod
    def explain_disruption(self, context: dict[str, Any]) -> str:
        """Turn raw disruption facts (cause, delay, ops note) into a plain-English explanation."""
        raise NotImplementedError

    @abstractmethod
    def describe_risk(self, context: dict[str, Any]) -> str:
        """Turn a computed connection-risk assessment into a short passenger-facing summary."""
        raise NotImplementedError

    @abstractmethod
    def recommend_reroute(self, context: dict[str, Any]) -> str:
        """Turn a ranked list of reroute options into a short recommendation with rationale."""
        raise NotImplementedError
