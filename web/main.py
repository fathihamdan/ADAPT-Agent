"""ADAPT-Agent web app: serves the ADAPT UI (the React app in
"Flight Disruption Assistant (UI)") and the API it calls.

Endpoints wrap the same adapt/agents used by the CLI - no separate logic, just a
JSON-shaped view of the same orchestrator output.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from adapt.utils.env import load_dotenv
from web import service

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
UI_DIST_DIR = REPO_ROOT / "Flight Disruption Assistant (UI)" / "dist"

if not UI_DIST_DIR.is_dir():
    raise RuntimeError(
        f"UI build not found at {UI_DIST_DIR}. Build it first:\n"
        f'  cd "{UI_DIST_DIR.parent}" && npx pnpm install && npx pnpm build'
    )

app = FastAPI(title="ADAPT-Agent")


class PassengerRouteSearch(BaseModel):
    passenger_name: str = Field(min_length=1, max_length=120)
    origin: str = Field(min_length=3, max_length=3)
    destination: str = Field(min_length=3, max_length=3)
    departure: datetime


@app.post("/api/passenger-search")
def api_search_passenger_routes(request: PassengerRouteSearch) -> dict:
    try:
        return service.search_passenger_routes(
            passenger_name=request.passenger_name,
            origin=request.origin,
            destination=request.destination,
            departure=request.departure,
        )
    except ValueError as exc:
        # Input problem the user can fix (same airport twice, unknown airport
        # code) - surface the message verbatim so the form can show it.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc


@app.get("/api/airports")
def api_list_airports() -> list[dict]:
    """Airports the passenger-search form can offer - code, city and name."""
    return service.list_airports()


@app.get("/api/status")
def api_status() -> dict:
    return service.get_system_status()


@app.get("/api/flights")
def api_list_flights(
    limit: int = 200,
    origin: str | None = None,
    destination: str | None = None,
    disrupted: bool = False,
) -> list[dict]:
    """Flights for the Flights table, newest departure first.

    Served from the locally harvested database when it has data (free, and
    typically hundreds of rows), otherwise the live API, otherwise mock. The
    default limit is well above the old 25 because the local DB is the normal
    source now and a 400-row table is the point of harvesting.
    """
    return service.list_flights(
        limit=max(1, min(limit, 2000)),
        origin=origin,
        destination=destination,
        disrupted=disrupted,
    )


@app.get("/api/queue")
def api_list_queue() -> list[dict]:
    """Every passenger with at least one detected connection, pre-computed risk,
    sorted worst-first. Passengers with no connection aren't included - nothing
    for an ops desk to watch on a single-flight booking.
    """
    return service.list_passenger_queue()


@app.post("/api/queue/refresh")
def api_refresh_queue() -> list[dict]:
    """Manual refresh: forces fresh live AviationStack lookups for PSG1002's real
    flight. GET /api/queue otherwise reuses whatever was built once at server
    start (or the last refresh) - no automatic re-fetching on every request.
    """
    return service.refresh_queue()


class RerouteConfirmation(BaseModel):
    """The option the ops desk picked for this passenger."""

    code: str
    route: str = ""
    depart: str = ""
    arrival: str = ""
    delay_vs_original: int = 0
    connections: int = 0


@app.post("/api/queue/{passenger_id}/reroute")
def api_confirm_reroute(passenger_id: str, option: RerouteConfirmation) -> dict:
    """Mark a passenger as rebooked: drops out of the queue, into Rerouted."""
    result = service.confirm_reroute(passenger_id, option.model_dump())
    if result is None:
        raise HTTPException(status_code=404, detail=f"No passenger found with ID '{passenger_id}'")
    return result


@app.get("/api/rerouted")
def api_list_rerouted() -> list[dict]:
    """Passengers the desk has already rebooked, most recent first."""
    return service.list_rerouted_passengers()


@app.delete("/api/rerouted/{passenger_id}")
def api_undo_reroute(passenger_id: str) -> dict:
    """Put a passenger back in the queue - the escape hatch for a misclick."""
    if not service.undo_reroute(passenger_id):
        raise HTTPException(status_code=404, detail=f"'{passenger_id}' is not marked as rerouted")
    return {"passenger_id": passenger_id, "restored": True}


@app.post("/api/flights/refresh")
def api_refresh_flights(pages: int = 3) -> dict:
    """Fetch the newest flights from AviationStack into the local database.

    Costs `pages` API calls against a ~100-call monthly quota, so it is a button
    the user presses rather than anything automatic.
    """
    return service.refresh_flight_database(pages=max(1, min(pages, 10)))


@app.get("/api/queue/{passenger_id}")
def api_get_passenger(passenger_id: str) -> dict:
    try:
        detail = service.build_passenger_detail(passenger_id)
    except RuntimeError as exc:
        # Raised by the active LLM client (Anthropic/OpenRouter) with an already-clean
        # message - surface it as-is rather than a raw 500 stack trace.
        raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No passenger found with ID '{passenger_id}'")
    return detail


@app.get("/api/track/{flight_iata}")
def api_track_flight(flight_iata: str) -> dict:
    try:
        result = service.build_live_track(flight_iata)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No live AviationStack data found for flight '{flight_iata}'.",
        )
    return result


app.mount("/", StaticFiles(directory=UI_DIST_DIR, html=True), name="static")
