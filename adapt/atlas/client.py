"""Atlas Flight CLI wrapper — the only file that shells out to `atlas-flight`.

Responsibilities:
  * locate the `atlas-flight` executable (PATH or uv tool dir)
  * check authorization status
  * run a search for a single (origin, destination, departure date, adults) tuple
  * parse the JSON response envelope and convert offers to `AtlasOffer`

Failure modes are typed:
  * `AtlasUnavailable` — the CLI itself is missing or not executable; the
    caller should fall back to mock data without scaring the user.
  * `AtlasError` — the CLI ran but returned a non-success `code` the caller
    cannot use (auth required, rate limit, upstream failure, etc.).

The wrapper never inspects credentials, never retries on its own, and never
mutates anything. Side-effecting Atlas commands (order, pay) are intentionally
not exposed — ADAPT currently uses Atlas for discovery only.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# The minimum CLI version the contract was validated against.
MIN_CLI_VERSION = (0, 3, 12)

# Commands are intentionally frozen to the documented contract.
_SEARCH_CMD = (
    "search",
    "--origin",
    "--destination",
    "--depart",
    "--adults",
    "--json",
)


class AtlasUnavailable(RuntimeError):
    """Raised when the atlas-flight CLI cannot be located or executed."""


class AtlasError(RuntimeError):
    """Raised when the CLI ran but returned a non-success envelope.

    `code` is the Atlas response code (e.g. AUTHORIZATION_REQUIRED,
    FLIGHT_SEARCH_FAILED). `message` is the Atlas human-facing text — shown to
    the operator for diagnostics but never used for branching.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class AtlasSegment:
    """One flight segment inside an Atlas offer (one row of the itinerary)."""

    carrier: str
    operating_carrier: str | None
    flight_number: str
    origin: str
    destination: str
    departure: datetime
    arrival: datetime
    duration_minutes: int
    cabin_class: int


@dataclass
class AtlasOffer:
    """One Atlas search offer, normalised for ADAPT's reroute ranking.

    All IDs are opaque strings and must be preserved byte-for-byte if a later
    stage (verify / order) is ever wired up.
    """

    offer_id: str
    search_id: str
    carrier: str
    flight_number: str
    origin: str
    destination: str
    departure: datetime
    arrival: datetime
    duration_minutes: int
    cabin_class: int
    currency: str
    total_price: float
    base_fare: float
    tax: float
    price_status: str  # "reference" or "current"
    bookable: bool
    ancillary_supported: list[str] = field(default_factory=list)
    operating_carrier: str | None = None
    segments: list[AtlasSegment] = field(default_factory=list)

    @property
    def is_reference_only(self) -> bool:
        return self.price_status == "reference" or not self.bookable

    @property
    def connections(self) -> int:
        return max(0, len(self.segments) - 1)

    def legs_summary(self) -> str:
        """Human-readable one-liner, e.g. 'EI7112 + EI160 via DUB'."""
        if not self.segments:
            return f"{self.flight_number} ({self.origin} -> {self.destination})"
        flight_nos = " + ".join(s.flight_number for s in self.segments)
        if self.connections == 0:
            return flight_nos
        via = " -> ".join(s.destination for s in self.segments[:-1])
        return f"{flight_nos} (via {via})"


def _find_atlas_binary() -> str:
    """Return the absolute path of the `atlas-flight` executable.

    Search order:
      1. `atlas-flight` on PATH.
      2. uv tool bin dir (Windows: %LOCALAPPDATA%\\.local\\bin, POSIX: $HOME/.local/bin).
    Raises `AtlasUnavailable` if neither is found.
    """
    on_path = shutil.which("atlas-flight")
    if on_path:
        return on_path

    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".local", "bin", "atlas-flight.exe"),
        os.path.join(home, ".local", "bin", "atlas-flight"),
    ]
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(os.path.join(local_appdata, ".local", "bin", "atlas-flight.exe"))

    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK | os.R_OK):
            return candidate

    raise AtlasUnavailable(
        "atlas-flight CLI not found on PATH and not in the uv tool bin directory. "
        "Install it with:  uv tool install --force --python 3.12 atlas-flight-booking==0.3.12"
    )


def _parse_version(output: str) -> tuple[int, ...]:
    """Parse `atlas-flight X.Y.Z` output into a tuple; raises AtlasUnavailable on any mismatch."""
    line = output.strip().splitlines()[0] if output.strip() else ""
    if not line.startswith("atlas-flight "):
        raise AtlasUnavailable(f"Unexpected atlas-flight version output: {output!r}")
    version_str = line.split(" ", 1)[1].strip()
    try:
        return tuple(int(p) for p in version_str.split("."))
    except ValueError as exc:
        raise AtlasUnavailable(f"Could not parse atlas-flight version from {output!r}") from exc


class AtlasClient:
    """Talks to the `atlas-flight` CLI. One instance per operation is fine."""

    def __init__(self, binary: str | None = None, timeout: int = 60) -> None:
        self._binary = binary or _find_atlas_binary()
        self._timeout = timeout
        self._check_version()

    # -- lifecycle ----------------------------------------------------------

    def _check_version(self) -> None:
        out = self._run_raw(["--version"])
        version = _parse_version(out)
        if version < MIN_CLI_VERSION:
            raise AtlasUnavailable(
                f"atlas-flight {version} is older than the minimum supported "
                f"{'.'.join(map(str, MIN_CLI_VERSION))}. Upgrade with: "
                "uv tool install --force --python 3.12 atlas-flight-booking==0.3.12"
            )

    def _run_raw(self, args: list[str]) -> str:
        try:
            result = subprocess.run(
                [self._binary, *args],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise AtlasUnavailable(f"atlas-flight binary missing at {self._binary}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AtlasUnavailable(f"atlas-flight timed out after {self._timeout}s") from exc
        except OSError as exc:
            raise AtlasUnavailable(f"Could not execute atlas-flight: {exc}") from exc

        # The CLI writes JSON to stdout on success; diagnostics may land on stderr.
        # We branch on the parsed `code`, not on the exit code — but a non-zero
        # exit with no stdout is still a hard failure.
        if result.returncode != 0 and not result.stdout.strip():
            raise AtlasUnavailable(
                f"atlas-flight exited {result.returncode} with no output: "
                f"{result.stderr.strip() or 'no stderr'}"
            )
        return result.stdout

    def _run_json(self, args: list[str]) -> dict[str, Any]:
        out = self._run_raw(args)
        try:
            envelope = json.loads(out)
        except json.JSONDecodeError as exc:
            raise AtlasUnavailable(f"atlas-flight returned non-JSON output: {out[:200]!r}") from exc

        if not isinstance(envelope, dict) or "code" not in envelope:
            raise AtlasUnavailable(f"atlas-flight response missing 'code': {envelope!r}")

        code = envelope.get("code", "")
        if envelope.get("status") != "success":
            raise AtlasError(code, envelope.get("message", "unknown error"))
        return envelope

    # -- public API ---------------------------------------------------------

    def is_authorized(self) -> bool:
        """Return True only when `auth status` reports AUTHORIZED."""
        try:
            env = self._run_json(["auth", "status", "--json"])
        except AtlasUnavailable:
            return False
        except AtlasError:
            return False
        return env.get("code") == "AUTHORIZED" and bool(env.get("data", {}).get("authenticated"))

    def search(
        self,
        *,
        origin: str,
        destination: str,
        depart: datetime,
        adults: int = 1,
    ) -> list[AtlasOffer]:
        """Run one search and return normalised offers (may be empty).

        Raises `AtlasError` if the CLI returned a non-success code (e.g.
        AUTHORIZATION_REQUIRED). Raises `AtlasUnavailable` if the CLI itself
        could not be executed.
        """
        envelope = self._run_json(
            [
                "search",
                "--origin",
                origin.upper(),
                "--destination",
                destination.upper(),
                "--depart",
                depart.strftime("%Y-%m-%d"),
                "--adults",
                str(adults),
                "--json",
            ]
        )

        data = envelope.get("data", {}) or {}
        search_id = data.get("search_id", "")
        raw_offers = data.get("offers", []) or []
        if data.get("offer_count") and not raw_offers:
            return []

        results: list[AtlasOffer] = []
        for offer in raw_offers:
            segments = offer.get("segments", []) or []
            if not segments:
                continue
            first = segments[0]
            last = segments[-1]
            prices = offer.get("passenger_prices", []) or []
            total = offer.get("total_price")
            if total is None and prices:
                total = sum(p.get("subtotal", 0.0) for p in prices)
            base = sum(p.get("base_fare_per_passenger", 0.0) * p.get("count", 1) for p in prices)
            tax = sum(p.get("tax_per_passenger", 0.0) * p.get("count", 1) for p in prices)

            parsed_segments = [
                AtlasSegment(
                    carrier=s.get("carrier", ""),
                    operating_carrier=s.get("operating_carrier"),
                    flight_number=s.get("flight_number", ""),
                    origin=s.get("departure_airport", "").upper(),
                    destination=s.get("arrival_airport", "").upper(),
                    departure=_parse_compact_dt(s.get("departure_time", "")),
                    arrival=_parse_compact_dt(s.get("arrival_time", "")),
                    duration_minutes=int(s.get("duration_minutes", 0) or 0),
                    cabin_class=int(s.get("cabin_class", 1) or 1),
                )
                for s in segments
            ]

            results.append(
                AtlasOffer(
                    offer_id=offer.get("offer_id", ""),
                    search_id=search_id,
                    carrier=first.get("carrier", ""),
                    flight_number=first.get("flight_number", ""),
                    origin=first.get("departure_airport", "").upper(),
                    destination=last.get("arrival_airport", "").upper(),
                    departure=_parse_compact_dt(first.get("departure_time", "")),
                    arrival=_parse_compact_dt(last.get("arrival_time", "")),
                    duration_minutes=sum(s.duration_minutes for s in parsed_segments),
                    cabin_class=int(first.get("cabin_class", 1) or 1),
                    currency=offer.get("currency", "USD"),
                    total_price=float(total or 0.0),
                    base_fare=float(base),
                    tax=float(tax),
                    price_status=offer.get("price_status", "reference"),
                    bookable=bool(offer.get("bookable", False)),
                    ancillary_supported=list(offer.get("ancillary_supported", []) or []),
                    operating_carrier=first.get("operating_carrier"),
                    segments=parsed_segments,
                )
            )
        return results


def _parse_compact_dt(value: str) -> datetime:
    """Parse `YYYYMMDDHHmm` timestamps as returned by the Atlas search segments."""
    if not value:
        return datetime.min
    try:
        return datetime.strptime(value, "%Y%m%d%H%M")
    except ValueError:
        return datetime.min
