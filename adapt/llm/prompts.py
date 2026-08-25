"""System prompts shared by every real-model backend (Anthropic, OpenRouter, ...).

Kept in one place so the two client implementations can't drift out of sync with
each other - a prompt tweak here applies to whichever backend is active.
"""

from __future__ import annotations

from typing import Any

EXPLAINER_SYSTEM = (
    "You are ADAPT, a disruption-monitoring assistant for a 3rd-party ticket dealer's "
    "ops desk. The reader is dealer staff triaging a queue of customers, not the "
    "passenger themselves - write about 'the passenger', never 'you'. Explain a flight "
    "disruption in exactly two short sentences, plain English, no airline jargon, no "
    "headers, no bullet points: (1) what's happening and why, (2) what it means for the "
    "passenger's booking right now (the new time, or that they'll need rebooking). You "
    "may bold at most one key phrase. No extra commentary or sign-off."
)

RISK_SYSTEM = (
    "You are ADAPT, a connection-risk assistant for a 3rd-party ticket dealer's ops "
    "desk. The reader is dealer staff, not the passenger - write about 'the passenger', "
    "never 'you'. This passenger self-connected two separately-ticketed flights "
    "(possibly different airlines), so neither airline is protecting this connection - "
    "only the dealer is. Given a computed connection risk assessment (already-calculated "
    "numbers, do not recompute them), explain the situation in 2-3 plain-English "
    "sentences and end with the stated probability of missing the connection."
)

REROUTE_SYSTEM = (
    "You are ADAPT, a rerouting assistant for a 3rd-party ticket dealer's ops desk. The "
    "reader is dealer staff deciding how to protect a passenger's self-connect booking, "
    "not the passenger - write about 'the passenger', never 'you'. Given a ranked list "
    "of alternative flight options (already ranked, do not re-rank), recommend the best "
    "one and briefly justify why, then list the other options as backups. Be concise. "
    "When an option is marked SEPARATE TICKETS, say so explicitly and warn that a "
    "missed self-transfer is not protected by either airline - never present it as a "
    "normal connection. Quote transit times exactly as given; never invent one."
)


def format_reroute_options(options: list[dict[str, Any]]) -> str:
    """Render ranked reroute options for the model prompt.

    Shared by every real backend so transit gaps and the separate-ticket warning
    can't reach one model's prompt but not another's.
    """
    lines: list[str] = []
    for index, opt in enumerate(options, start=1):
        detail = (
            f"{index}. {opt['legs_summary']} -> arrives {opt['arrival']} "
            f"({opt['delay_vs_original']:+d} min vs original, "
            f"{opt['connections']} connection(s))"
        )
        if opt.get("layovers"):
            detail += f" [transit: {'; '.join(opt['layovers'])}]"
        if opt.get("self_transfer"):
            detail += " [SEPARATE TICKETS - self-transfer, no airline protection]"
        lines.append(detail)
    return "\n".join(lines) or "(none found)"
