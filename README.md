# ADAPT-Agent
## Airline Disruption Analysis &amp; Prevention Technology  
An Agentic AI-Powered system 

Flight delays, cancellations, and missed connections are a traveler's worst nightmare. The ADAPT Agent (Airline Disruption Analysis & Prevention Technology) is an innovative agentic AI solution designed to transform this stressful experience into a seamless, autonomous journey. ADAPT empowers passengers by providing intelligent insights and proactive solutions, ensuring you stay ahead of disruptions and reach your destination with minimal hassle.


## How ADAPT Revolutionizes Your Travel Experience:
ADAPT offers an end-to-end autonomous disruption management experience through its intelligent features and automated actions:

**- Disruption Explainer:** No more deciphering cryptic airline announcements. ADAPT translates complex technical information regarding delays, cancellations, weather events, and Air Traffic Control (ATC) issues into clear, easy-to-understand explanations. Know exactly what's happening and why.  

**- Connection Risk Predictor:** Traveling with connections? ADAPT calculates the precise probability of you missing your connecting flight. It intelligently analyzes critical factors such as your layover duration, terminal distances, and estimated walking times, providing you with real-time risk assessments.  

**- Rerouting Connection:** When disruptions strike, ADAPT acts swiftly. Our system proactively identifies and recommends optimal alternative flights and routes, presenting you with the best options to mitigate delays and avoid missed connections.

## CLI Prototype

This repo currently ships the CLI-first prototype (a web UI will follow once the
design is ready). It runs fully offline out of the box (rule-based explanations,
no API key needed) and drops in real Claude-generated explanations the moment
you set `ANTHROPIC_API_KEY`.

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

### Usage

```
adapt status                    # which LLM backend is active
adapt flights                   # list the mock flight schedule
adapt itineraries                # list sample passenger itineraries (PNRs)

adapt explain AD1402             # Disruption Explainer for one flight
adapt risk ADPT01                # Connection Risk Predictor for an itinerary
adapt reroute ORD LAX            # Rerouting Recommender, ad-hoc search

adapt analyze ADPT01             # full agent: explain + risk + reroute, end-to-end
```

Sample itineraries to try with `analyze`:
- `ADPT01` — John Carter: weather delay eats a tight ORD connection (critical risk → reroute)
- `ADPT02` — Maria Gomez: DFW–ATL leg cancelled for mechanical reasons → reroute to keep the LHR connection
- `ADPT03` — Sam Lee: single-leg ATC delay, no connection to assess

### Architecture

- `adapt/models.py` — domain types (Flight, Itinerary, ConnectionRisk, RerouteOption)
- `adapt/data/mock_data.py` — mock flight schedule & itineraries (swap for a real flight-data API later)
- `adapt/llm/` — pluggable LLM backend: `MockLLMClient` (offline, default) or `AnthropicClient` (when `ANTHROPIC_API_KEY` is set); both implement the same `LLMClient` interface
- `adapt/agents/` — the three features (`disruption_explainer`, `connection_risk`, `rerouting`) plus `orchestrator.py`, which is the agentic layer: given an itinerary, it decides autonomously which of the three to run and in what order
- `adapt/cli.py` — Typer CLI wiring it all together
- `adapt/utils/formatting.py` — Rich-based terminal output

### Notes on the risk model

Connection risk is computed deterministically (not by the LLM) from: inbound
delay, scheduled layover, whether a terminal change is required, and an
estimated walking time — the LLM only narrates the result. This keeps risk
scoring reproducible and auditable; swap `adapt/agents/connection_risk.py`'s
formula for a real predictive model later without touching the CLI or the
orchestrator.
