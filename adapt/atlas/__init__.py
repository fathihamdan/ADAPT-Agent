"""Atlas Flight API integration for ADAPT-Agent.

This package is a thin, defensive wrapper around the `atlas-flight` CLI
(https://github.com/atlas-doc/atlas-flight-booking-skill) -- the same CLI that
powers the Atlas Flight Booking Skill in Qoder. ADAPT uses it as an optional
live data source for reroute recommendations and as the booking engine for
autonomous flight booking through the ADAPT agent.

The wrapper speaks only the documented JSON contract from
`references/cli-contract.md` -- branch on `code`, never on `message`, and treat
every ID as opaque.
"""

from __future__ import annotations

from adapt.atlas.client import (
    AtlasClient,
    AtlasError,
    AtlasOffer,
    AtlasSegment,
    AtlasUnavailable,
)

__all__ = ["AtlasClient", "AtlasError", "AtlasOffer", "AtlasSegment", "AtlasUnavailable"]
