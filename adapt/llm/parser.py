"""Flight-request parsing helpers shared across LLM backends.

Used as the fallback when the active LLM backend cannot (or should not) parse
a natural-language request itself. The parser extracts the four inputs Atlas
needs — origin, destination, departure date, adult count — from free text.

It is intentionally tolerant:

* Airport codes (2-3 uppercase letters) or city names via the CITY_ALIASES map.
* Relative dates ("tomorrow", "next friday", "in 3 days") as well as absolute
  ones ("26 September 2026", "2026-09-26", "sep 26").
* Passenger counts default to 1 adult when unspecified.

Anything the parser cannot resolve is left as None so the caller can prompt
the user for the missing piece.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

# Common city-name -> IATA code shortcuts. Airport codes themselves are passed
# through unchanged (e.g. "NRT" stays "NRT").
CITY_ALIASES: dict[str, str] = {
    # Asia
    "tokyo": "NRT", "nrt": "NRT", "haneda": "HND", "hnd": "HND",
    "osaka": "KIX", "kix": "KIX", "itami": "ITM",
    "shanghai": "PVG", "pudong": "PVG", "pvg": "PVG", "hongqiao": "SHA", "sha": "SHA",
    "beijing": "PEK", "pek": "PEK",
    "seoul": "ICN", "icn": "ICN", "gimpo": "GMP",
    "hong kong": "HKG", "hkg": "HKG",
    "singapore": "SIN", "sin": "SIN",
    "bangkok": "BKK", "bkk": "BKK",
    "taipei": "TPE", "tpe": "TPE",
    # Europe
    "london": "LHR", "lhr": "LHR", "heathrow": "LHR", "gatwick": "LGW",
    "paris": "CDG", "cdg": "CDG", "amsterdam": "AMS", "ams": "AMS",
    "dublin": "DUB", "dub": "DUB", "frankfurt": "FRA", "fra": "FRA",
    "madrid": "MAD", "mad": "MAD", "rome": "FCO", "fco": "FCO",
    # Americas
    "new york": "JFK", "jfk": "JFK", "new york city": "JFK", "nyc": "JFK",
    "los angeles": "LAX", "lax": "LAX", "san francisco": "SFO", "sfo": "SFO",
    "chicago": "ORD", "ord": "ORD", "o'hare": "ORD",
    "atlanta": "ATL", "atl": "ATL", "dallas": "DFW", "dfw": "DFW",
    "miami": "MIA", "mia": "MIA", "denver": "DEN", "den": "DEN",
    "seattle": "SEA", "sea": "SEA", "boston": "BOS", "bos": "BOS",
    "toronto": "YYZ", "yyz": "YYZ", "mexico city": "MEX", "mex": "MEX",
    # Middle East / Africa / Oceania
    "dubai": "DXB", "dxb": "DXB", "doha": "DOH", "doh": "DOH",
    "sydney": "SYD", "syd": "SYD", "melbourne": "MEL", "mel": "MEL",
    "cairo": "CAI", "cai": "CAI",
}

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_WEEKDAY_OFFSET = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


@dataclass
class ParsedFlightRequest:
    origin: str | None = None
    destination: str | None = None
    depart: date | None = None
    adults: int = 1
    # Whatever the parser could not resolve; used by the caller to re-prompt.
    missing: list[str] | None = None

    @property
    def is_complete(self) -> bool:
        return bool(self.origin and self.destination and self.depart)

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "depart": self.depart.isoformat() if self.depart else None,
            "adults": self.adults,
        }


def _resolve_airport(token: str) -> str | None:
    if not token:
        return None
    lowered = token.strip().lower()
    if lowered in CITY_ALIASES:
        return CITY_ALIASES[lowered]
    upper = token.strip().upper()
    if re.fullmatch(r"[A-Z]{2,3}", upper):
        return upper
    return None


def _parse_date(text: str, today: date | None = None) -> date | None:
    """Best-effort date parser for free-form English dates."""
    today = today or date.today()
    s = text.strip().lower()

    if s in {"today", "tonight"}:
        return today
    if s == "tomorrow":
        return today + timedelta(days=1)

    # "in N days" / "N days from now"
    m = re.search(r"in\s+(\d+)\s+days?", s)
    if m:
        return today + timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s+days?\s+from\s+(now|today)", s)
    if m:
        return today + timedelta(days=int(m.group(1)))

    # "next <weekday>"
    m = re.search(r"next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", s)
    if m:
        target = _WEEKDAY_OFFSET[m.group(1)]
        delta = (target - today.weekday()) % 7
        if delta == 0:
            delta = 7
        return today + timedelta(days=delta + 7)

    # "<weekday>" without "next" -> next occurrence (including today if matches)
    m = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", s)
    if m:
        target = _WEEKDAY_OFFSET[m.group(1)]
        delta = (target - today.weekday()) % 7
        return today + timedelta(days=delta)

    # "YYYY-MM-DD" or "YYYY/MM/DD"
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # "DD Mon YYYY" or "Mon DD, YYYY" or "Mon DD"
    m = re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", s)
    if m:
        month = _MONTHS.get(m.group(2))
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(1)))
            except ValueError:
                pass

    m = re.search(r"([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?", s)
    if m:
        month = _MONTHS.get(m.group(1))
        if month:
            year = int(m.group(3)) if m.group(3) else today.year
            if month < today.month or (month == today.month and int(m.group(2)) < today.day):
                year = max(year, today.year + 1)
            try:
                return date(year, month, int(m.group(2)))
            except ValueError:
                pass

    return None


_FROM_TO_RE = re.compile(
    r"(?:from|depart(?:ing|ure)?\s+(?:from)?|outbound|leaving(?:\s+from)?|fly(?:ing)?)\s+"
    r"([a-zA-Z]{2,}(?:\s+[a-zA-Z]+?)?)\s+"
    r"(?:to|->|→|arriv(?:ing|al)?(?:\s+(?:at|in))?|heading\s+to|fly(?:ing)?\s+to)\s+"
    r"([a-zA-Z][a-zA-Z ]+?)(?=\s+(?:on|for|depart|leaving|around|about|tomorrow|today|tonight|next|this|in\s+\d|\d{1,2}(?:st|nd|rd|th)?\s+[a-z]|[a-z]+\s+\d{1,2}|monday|tuesday|wednesday|thursday|friday|saturday|sunday|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\b|[,\s]*$)",
    re.IGNORECASE,
)

_DATE_RE = re.compile(
    r"\b(?:tomorrow|today|tonight)\b"
    r"|(?:on|for|depart(?:ing)?|leaving(?:\s+on)?|around|about)\s+"
    r"(\d{1,2}(?:st|nd|rd|th)?\s+[a-z]+\s+\d{4}"
    r"|[a-z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?"
    r"|\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    r"|next\s+[a-z]+)"
    r"|(?:in\s+\d+\s+days?)"
    r"|(\d{4}[-/]\d{1,2}[-/]\d{1,2})"
    r"|\b(next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b"
    # Bare month(+day) without a preceding preposition — catches "tokyo october 15".
    r"|\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|"
    r"january|february|march|april|june|july|august|september|"
    r"october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?)\b",
    re.IGNORECASE,
)

_ADULT_RE = re.compile(r"(\d+)\s*(?:adults?|passengers?|pax|people|persons?)", re.IGNORECASE)


def parse_flight_request(text: str, today: date | None = None) -> ParsedFlightRequest:
    """Extract (origin, destination, departure date, adults) from free English text."""
    today = today or date.today()
    result = ParsedFlightRequest()

    match = _FROM_TO_RE.search(text)
    if match:
        result.origin = _resolve_airport(match.group(1))
        result.destination = _resolve_airport(match.group(2))

    # If the from/to pattern didn't match, fall back to two consecutive
    # city-or-code tokens separated by "to" / "->". Each side takes up to
    # two words so multi-word cities like "New York" / "San Francisco"
    # parse, and the lookahead stops the destination group before a date.
    if not (result.origin and result.destination):
        # Pre-tokenise: find the "to"/"->" separator and pull the destination
        # token(s) that end before a date-like token or end-of-string.
        m = re.search(
            r"\b([a-zA-Z]{2,}(?:\s+[a-zA-Z]+)?)\s+(?:to|->|→)\s+"
            r"((?:[a-zA-Z]{2,}\s+){0,2}[a-zA-Z]{2,})"
            r"(?=\s*(?:[,\s]+|\s+on\b|\s+for\b|\s+depart\b|\s+leaving\b|\s+tomorrow\b|\s+today\b|\s+tonight\b|\s+next\b|\s+in\s+\d|\s+\d{1,2}(?:st|nd|rd|th)?\b|\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\b|\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b)|$)",
            text,
            re.IGNORECASE,
        )
        if m:
            # Trim trailing month / weekday tokens from the captured destination.
            dest = m.group(2)
            trailing = re.split(
                r"\s+(?=(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|"
                r"january|february|march|april|june|july|august|september|"
                r"october|november|december|monday|tuesday|wednesday|thursday|"
                r"friday|saturday|sunday)\b)",
                dest,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]
            result.origin = result.origin or _resolve_airport(m.group(1))
            result.destination = result.destination or _resolve_airport(trailing)

    date_match = _DATE_RE.search(text)
    if date_match:
        # Capture groups (by index):
        #   1 = "on <date>" inner group
        #   2 = bare YYYY-MM-DD
        #   3 = "next <weekday>"
        #   4 = bare "<month> <day>"
        # For the today/tomorrow/tonight and "in N days" branches, there is no
        # inner capture — use group(0) (the whole match) as fallback.
        date_text = (
            date_match.group(1)
            or date_match.group(2)
            or date_match.group(3)
            or date_match.group(4)
            or date_match.group(0)
        )
        result.depart = _parse_date(date_text, today)

    adult_match = _ADULT_RE.search(text)
    if adult_match:
        try:
            result.adults = max(1, min(9, int(adult_match.group(1))))
        except ValueError:
            result.adults = 1

    result.missing = [
        field
        for field in ("origin", "destination", "depart")
        if getattr(result, field) is None
    ]
    return result
