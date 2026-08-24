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
    "beijing": "PEK", "pek": "PEK", "daxing": "PKX", "pkx": "PKX",
    "seoul": "ICN", "icn": "ICN", "gimpo": "GMP", "gmp": "GMP",
    "hong kong": "HKG", "hkg": "HKG",
    "singapore": "SIN", "sin": "SIN",
    "bangkok": "BKK", "bkk": "BKK", "don mueang": "DMK", "dmk": "DMK",
    "kuala lumpur": "KUL", "kul": "KUL",
    "jakarta": "CGK", "cgk": "CGK",
    "manila": "MNL", "mnl": "MNL",
    "hanoi": "HAN", "han": "HAN",
    "ho chi minh": "SGN", "saigon": "SGN", "sgn": "SGN",
    "taipei": "TPE", "tpe": "TPE",
    "mumbai": "BOM", "bom": "BOM", "delhi": "DEL", "del": "DEL",
    "chengdu": "CTU", "ctu": "CTU", "guangzhou": "CAN", "can": "CAN",
    "shenzhen": "SZX", "szx": "SZX", "xiamen": "XMN", "xmn": "XMN",
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
    "abu dhabi": "AUH", "auh": "AUH",
    "istanbul": "IST", "ist": "IST",
    "sydney": "SYD", "syd": "SYD", "melbourne": "MEL", "mel": "MEL",
    "auckland": "AKL", "akl": "AKL",
    "cairo": "CAI", "cai": "CAI",
    "johannesburg": "JNB", "jnb": "JNB",
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

    # "next week" -> 7 days from today
    if s in ("next week", "in a week", "in one week"):
        return today + timedelta(days=7)
    m = re.search(r"in\s+(\d+)\s+weeks?", s)
    if m:
        return today + timedelta(weeks=int(m.group(1)))

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

    # "DD Mon YYYY" or "DD Mon" (year defaults to next occurrence)
    m = re.search(r"(\d{1,2})\s+([a-z]+)(?:\s+(\d{4}))?", s)
    if m:
        month = _MONTHS.get(m.group(2))
        if month:
            year = int(m.group(3)) if m.group(3) else today.year
            day = int(m.group(1))
            if not m.group(3):  # no year given -- pick next occurrence
                try:
                    candidate = date(year, month, day)
                except ValueError:
                    candidate = None
                if candidate and candidate < today:
                    year = today.year + 1
            try:
                return date(year, month, day)
            except ValueError:
                pass

    # "Mon DD, YYYY" or "Mon DD" (year optional)
    m = re.search(r"([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?", s)
    if m:
        month = _MONTHS.get(m.group(1))
        if month:
            year = int(m.group(3)) if m.group(3) else today.year
            day = int(m.group(2))
            if not m.group(3):  # no year given -- pick next occurrence
                try:
                    candidate = date(year, month, day)
                except ValueError:
                    candidate = None
                if candidate and candidate < today:
                    year = today.year + 1
            try:
                return date(year, month, day)
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
    r"(\d{1,2}(?:st|nd|rd|th)?\s+[a-z]+(?:\s+\d{4})?"
    r"|[a-z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?"
    r"|\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    r"|next\s+[a-z]+)"
    r"|(?:in\s+\d+\s+(?:days?|weeks?))"
    r"|\b(?:next\s+week)\b"
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
        # Fallback: split on "to" / "->" / unicode arrow to find origin and
        # destination. Take the last word(s) before "to" as origin, first
        # word(s) after "to" as destination (stopping before any date keyword).
        m = re.search(
            r"\b([a-zA-Z]{2,}(?:\s+[a-zA-Z]+)?)\s+(?:to|->|\u2192)\s+([a-zA-Z]{2,}(?:\s+[a-zA-Z]+)?)",
            text,
            re.IGNORECASE,
        )
        if m:
            raw_origin = m.group(1)
            raw_dest = m.group(2)
            # Trim trailing date keywords from destination (e.g. "Tokyo next" -> "Tokyo").
            _date_kw = {
                "on", "for", "depart", "departing", "leaving", "tomorrow", "today",
                "tonight", "next", "this", "in", "between", "and",
                "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept",
                "oct", "nov", "dec", "january", "february", "march", "april", "june",
                "july", "august", "september", "october", "november", "december",
                "week", "weeks",
            }
            dest_words = raw_dest.split()
            trimmed = [w for w in dest_words if w.lower() not in _date_kw]
            if trimmed:
                raw_dest = " ".join(trimmed)
            origin_words = raw_origin.split()
            trimmed_origin = [w for w in origin_words if w.lower() not in _date_kw]
            if trimmed_origin:
                raw_origin = " ".join(trimmed_origin)
            result.origin = result.origin or _resolve_airport(raw_origin)
            result.destination = result.destination or _resolve_airport(raw_dest)

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
