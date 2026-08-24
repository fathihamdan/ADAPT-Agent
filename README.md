# ADAPT-Agent
## Airline Disruption Analysis &amp; Prevention Technology  
An Agentic AI-Powered system 

Self-connect trips — flight A on one airline, flight B on a different one, sold as a single journey by a 3rd-party ticket dealer — are a liability nobody but the dealer is watching. Neither airline protects that connection if flight A runs late; they don't even know the other flight exists. ADAPT-Agent (Airline Disruption Analysis & Prevention Technology) is an agentic AI tool for that dealer's **ops desk**: it watches every customer's self-connect booking, explains what's going wrong in plain English, predicts the real probability of a missed connection, and finds a rerouting option before the customer ever reaches the gate.

## How ADAPT Revolutionizes Disruption Ops:
ADAPT offers an end-to-end autonomous disruption management experience through its intelligent features and automated actions:

**- Disruption Explainer:** No more deciphering cryptic airline announcements. ADAPT translates complex technical information regarding delays, cancellations, weather events, and Air Traffic Control (ATC) issues into clear, easy-to-understand explanations for the ops desk. Know exactly what's happening and why, for every passenger in the queue.

**- Connection Risk Predictor:** For every passenger who self-connected two separately-ticketed flights, ADAPT detects the real connection and calculates the precise probability of missing it. It intelligently analyzes critical factors such as layover duration, terminal distances, and estimated walking times, providing real-time risk assessments — sorted worst-first.

**- Rerouting Connection:** When disruptions strike, ADAPT acts swiftly. Our system proactively identifies and recommends optimal alternative flights and routes, presenting the ops desk with the best options to protect the customer's trip.

## CLI Prototype

This repo currently ships the CLI-first prototype (a web UI follows the same data,
in `Flight Disruption Assistant (UI)/`). It runs fully offline out of the box
(rule-based explanations, no API key needed) and drops in real Claude-generated
explanations the moment you set `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY`.

### Setup

```
python -m venv .venv
.venv/Scripts/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e .
```

To use real Claude-generated explanations instead of the offline rule-based ones:

```
pip install -e ".[anthropic]"
export ANTHROPIC_API_KEY=sk-ant-...   # PowerShell: $env:ANTHROPIC_API_KEY = "sk-ant-..."
```

(Or set `OPENROUTER_API_KEY` to route through OpenRouter instead — see `adapt/llm/openrouter_client.py`.)

### Usage

```
adapt status                    # which backends are active (LLM, rerouting, live tracking)
adapt flights                   # list the mock flight schedule
adapt passengers                # list passengers with a detected self-connect booking

adapt explain NA1402             # Disruption Explainer for one flight
adapt track AA100                # Disruption Explainer for any real flight, via AviationStack
adapt risk PSG1001                # Connection Risk Predictor for a passenger
adapt reroute ORD LAX            # Rerouting Recommender, ad-hoc search

adapt analyze PSG1001            # full agent: explain + risk + reroute, end-to-end
```

Sample passengers to try with `analyze` — every one books flight A and flight B on
**different** fictional airlines, the way a self-connect dealer actually sells them:

- `PSG1001` — John Carter: Northbridge Air → Kansai Wing, weather delay eats a tight NRT connection (critical risk → reroute, using a real Atlas-covered route so the Rerouting Recommender pulls live alternatives)
- `PSG1002` — Maria Gomez: Northbridge Air → Skyline Connect, first leg cancelled (mechanical) → reroute to keep the LHR connection; the cancelled leg is swapped live for a real currently-disrupted flight from AviationStack when configured
- `PSG1003` — Sam Lee: Northbridge Air → Skyline Connect, a comfortable-but-real MEDIUM-risk connection — the queue isn't only crises

Passengers with only one flight aren't modeled at all: there's no connection for
this tool to watch, so there's nothing to show.

### Architecture

- `adapt/models.py` — domain types (`Flight`, `Passenger`, `ConnectionRisk`, `RerouteOption`). A `Passenger` owns a flat list of booked flights — not pre-paired, not pre-ordered, and not tied to one airline's PNR
- `adapt/agents/connections.py` — `find_connections()`: detects which of a passenger's flights actually connect (same airport, chronologically valid), so nothing has to pre-declare a pairing
- `adapt/data/mock_data.py` — mock flight schedule & self-connect passengers (swap for a real flight-data / booking-dealer API later)
- `adapt/llm/` — pluggable LLM backend: `MockLLMClient` (offline, default), `AnthropicClient`, or `OpenRouterClient`; all three implement the same `LLMClient` interface and speak in ops-desk phrasing ("the passenger", not "you")
- `adapt/agents/` — the three features (`disruption_explainer`, `connection_risk`, `rerouting`) plus `orchestrator.py`, the agentic layer: given a passenger, it detects connections and decides autonomously which of the three to run and in what order
- `adapt/cli.py` — Typer CLI wiring it all together
- `adapt/utils/formatting.py` — Rich-based terminal output
- `web/` — FastAPI backend serving the same agents as a JSON API (`/api/queue` for the triage list, `/api/queue/{passenger_id}` for detail) plus the built React ops dashboard

### Notes on the risk model

Connection risk is computed deterministically (not by the LLM) from: inbound
delay, scheduled layover, whether a terminal change is required, and an
estimated walking time — the LLM only narrates the result. This keeps risk
scoring reproducible and auditable; swap `adapt/agents/connection_risk.py`'s
formula for a real predictive model later without touching the CLI, the API,
or the orchestrator.
