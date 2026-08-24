"""ADAPT-Agent web app: serves the GateWatch UI (the React app in
"Flight Disruption Assistant (UI)") and the API it calls.

Endpoints wrap the same adapt/agents used by the CLI - no separate logic, just a
JSON-shaped view of the same orchestrator output.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

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


@app.get("/api/status")
def api_status() -> dict:
    return service.get_system_status()


@app.get("/api/flights")
def api_list_flights() -> list[dict]:
    return service.list_flights()


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
