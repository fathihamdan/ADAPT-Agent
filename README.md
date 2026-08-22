# ADAPT-Agent
## Airline Disruption Analysis &amp; Prevention Technology  
An Agentic AI-Powered system 

Flight delays, cancellations, and missed connections are a traveler's worst nightmare. The ADAPT Agent (Airline Disruption Analysis & Prevention Technology) is an innovative agentic AI solution designed to transform this stressful experience into a seamless, autonomous journey. ADAPT empowers passengers by providing intelligent insights and proactive solutions, ensuring you stay ahead of disruptions and reach your destination with minimal hassle.


## How ADAPT Revolutionizes Your Travel Experience:
ADAPT offers an end-to-end autonomous disruption management experience through its intelligent features and automated actions:

**- Disruption Explainer:** No more deciphering cryptic airline announcements. ADAPT translates complex technical information regarding delays, cancellations, weather events, and Air Traffic Control (ATC) issues into clear, easy-to-understand explanations. Know exactly what's happening and why.  

**- Connection Risk Predictor:** Traveling with connections? ADAPT calculates the precise probability of you missing your connecting flight. It intelligently analyzes critical factors such as your layover duration, terminal distances, and estimated walking times, providing you with real-time risk assessments.  

**- Rerouting Connection:** When disruptions strike, ADAPT acts swiftly. Our system proactively identifies and recommends optimal alternative flights and routes, presenting you with the best options to mitigate delays and avoid missed connections.  

**- Rescheduling & Rebooking Agent:** Recommending an alternative is only half the job — ADAPT carries it through to a ticket. Backed by the Atlas Flight API, the agent **discovers** live bookable inventory, **verifies** the real fare before you commit, offers **ancillaries** (baggage and seats), then completes **booking, payment and ticketing** — pausing for your explicit approval at every step that costs money. See [Autonomous rebooking via the Atlas Flight API](#autonomous-rebooking-via-the-atlas-flight-api).

## CLI Prototype

This repo currently ships the CLI-first prototype (a web UI will follow once the
design is ready). It runs fully offline out of the box (rule-based explanations,
no API key needed) and drops in real model-generated explanations the moment you
set an LLM key.

### Setup

```
python -m venv .venv
.venv/Scripts/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e .
```

To use real model-generated explanations instead of the offline rule-based ones,
set either key — OpenRouter is checked first, then Anthropic:

```
export OPENROUTER_API_KEY=sk-or-...   # PowerShell: $env:OPENROUTER_API_KEY = "sk-or-..."

pip install -e ".[anthropic]"         # only needed for the direct Anthropic backend
export ANTHROPIC_API_KEY=sk-ant-...   # PowerShell: $env:ANTHROPIC_API_KEY = "sk-ant-..."
```

Any of these can instead go in a `.env` file at the project root (`KEY=value`,
one per line). `adapt/utils/env.py` loads it on every CLI run, and `.env` is
gitignored.

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

## Autonomous rebooking via the Atlas Flight API

> **Status: design & integration contract — not yet implemented.** The commands
> and module paths in this section do not exist in the code yet; `adapt/atlas/`
> is unbuilt. This section is the agreed target contract so the implementation
> and the docs don't drift. The CLI commands documented under
> [Usage](#usage) above are the ones that work today.

`reroute` currently ends at a *recommendation* drawn from mock data. Atlas is
what turns that recommendation into a real, paid, ticketed itinerary — and it is
where ADAPT stops being an advisor and becomes an agent that acts.

### Credentials

Atlas does **not** use a single bearer API key. Every request is authenticated
with a **client ID + client secret pair sent as headers**. Generate them in ATRIP
under `Profile` → `My Profile` → `Company Information` → `Sandbox Info`.

```
# .env (project root, gitignored — never commit these)
ATLAS_CLIENT_ID=your-client-id
ATLAS_CLIENT_SECRET=your-client-secret
ATLAS_ENV=sandbox
```

Both values stay server-side. They must never reach a client app, a log line, or
a prompt sent to the LLM.

### Environments

| Env | Base URL | Behaviour |
| --- | --- | --- |
| `sandbox` | `https://sandbox.atriptech.com/` | Test inventory and test prices. No real booking, no real charge. |
| `production` | Two base URLs from ATRIP — one for `search` traffic, one for all other transaction APIs | Real money, real tickets. |

Switching environments invalidates every identifier you are holding. After a
switch, **start a new search** — never carry an offer across environments.

### Request conventions

- `POST /<endpoint>.do` with a JSON body — every Atlas call.
- Headers: `Content-Type: application/json`, `Accept: */*`,
  `Accept-Encoding: gzip`, `x-atlas-client-id`, `x-atlas-client-secret`.
- `Accept: */*` is mandatory. Atlas **rejects** `Accept: application/json`.
- Success is `status == 0`. Never branch on `msg` — it is human-facing text.
- `429` means rate-limited: honour the returned `retryAfter`, never retry-loop.

### The agent pipeline

The standard Atlas path is `search.do` → `verify.do` → `order.do` → `pay.do` →
`queryOrderDetails.do`, with ancillaries inserted before order creation. Each
stage maps to one agent capability:

| Stage | Atlas endpoint(s) | What the agent does | Gate |
| --- | --- | --- | --- |
| **1. Discover** | `search.do` (or `getOffers.do` when the target itinerary is already known) | Turn a disrupted itinerary into live, bookable candidates and rank them against the original arrival time | autonomous |
| **2. Verify** | `verify.do` | Recheck the real fare, routing and booking requirements before anything is committed | **stops on price increase** |
| **3. Ancillaries** | `getLuggage.do`, `seatAvailability.do` | Offer baggage and seats using the live `sessionId`/`OfferId` — never from flight data alone | optional, user-driven |
| **4. Book** | `order.do` (plus `orderCommit.do`, FR airlines only) | Create the order with passenger, document and contact details | **confirm passenger data** |
| **5. Pay & ticket** | `pay.do`, then poll `queryOrderDetails.do` | Pay, then follow the order until ticketing reaches a final state | **explicit payment approval** |

### Identifiers to carry between stages

| Identifier | Produced by | Valid for |
| --- | --- | --- |
| `routingIdentifier` | `search.do` | up to 6 hours |
| `sessionId` | `verify.do` | up to 2 hours |
| `orderNo` | `order.do` | until the order closes |
| airline PNR + `ticketNos` | `queryOrderDetails.do`, after ticketing | final result |

Treat both TTLs as upper bounds — fare and inventory can move well before they
expire, so re-verify rather than trusting an aging identifier. On the Fulfilment
API path (`getOfferPrice.do`) the payment and ticketing window is a **strict 5
minutes** after order creation.

### Rate limits

- `search.do` — 10 QPS
- `verify.do` and `getOffers.do` — share 60 QPM
- `seatAvailability.do` and `getLuggage.do` — share 60 QPM
- `order.do` and `pay.do` — not covered by the QPS/QPM policy

### Human-in-the-loop rails

The agent runs autonomously right up to the point where money or personal data
is committed. These are hard stops, not prompts the model may skip:

- **Price increase at verify** — show the previous and current total and require
  explicit acceptance of the new amount before continuing.
- **Before `order.do`** — display the itinerary, passenger name, document and
  contact details for confirmation.
- **Before `pay.do`** — display the full price breakdown, total, currency and
  payment deadline. Pay only on an unambiguous approval of *that exact* summary.
- **Seat selection** — collect a fallback choice up front, since a specific seat
  can become unavailable between query and order.
- **Payment ≠ ticketed** — never assume the two happen together. Poll
  `queryOrderDetails.do` to a final state; a webhook alone is not confirmation.

### Rehearsing the flow in Qoder (sandbox)

The Atlas Flight Booking Skill lets you exercise the whole pipeline in natural
language before writing any client code:

```
npx --yes skills add https://github.com/atlas-doc/atlas-flight-booking-skill --skill atlas-flight-booking
atlas-flight environment use sandbox --json
```

Then drive it conversationally — describe the route, date and passenger count;
pick an offer; verify the price; supply **fictional** passenger details; review
the order; and approve payment explicitly. The returned order number, PNR and
ticket number are sandbox test results. Switch back with
`atlas-flight environment use production --json` and start a fresh search.

### Planned shape

```
adapt/atlas/client.py       # transport: headers, gzip, status==0, 429/retryAfter
adapt/atlas/models.py       # Offer, VerifiedFare, AncillaryOption, Order, Ticket
adapt/agents/rebooking.py   # the five-stage machine + approval gates
```

The orchestrator hands off here: when a leg is cancelled or a connection scores
`HIGH`/`CRITICAL`, it proposes rebooking instead of merely listing alternatives.
Planned CLI surface:

```
adapt atlas status                              # env + credential check
adapt atlas discover NRT KIX 2026-09-04         # stage 1
adapt atlas verify <routingIdentifier>          # stage 2
adapt atlas ancillaries <sessionId>             # stage 3
adapt atlas book <sessionId>                    # stage 4
adapt atlas pay <orderNo>                       # stage 5
```

### Reference

- Atlas API documentation — <https://resources.atriptech.com/api-document/readme-1>
- Booking overview (paths, identifiers, limits) — <https://resources.atriptech.com/api-document/product-guides/booking/booking-overview>
- Skill repository — <https://github.com/atlas-doc/atlas-flight-booking-skill>

### Architecture

- `adapt/models.py` — domain types (Flight, Itinerary, ConnectionRisk, RerouteOption)
- `adapt/data/mock_data.py` — mock flight schedule & itineraries (swap for a real flight-data API later)
- `adapt/llm/` — pluggable LLM backend: `MockLLMClient` (offline, default), `OpenRouterClient` (when `OPENROUTER_API_KEY` is set) or `AnthropicClient` (when `ANTHROPIC_API_KEY` is set); all implement the same `LLMClient` interface
- `adapt/agents/` — the three features (`disruption_explainer`, `connection_risk`, `rerouting`) plus `orchestrator.py`, which is the agentic layer: given an itinerary, it decides autonomously which of the three to run and in what order
- `adapt/cli.py` — Typer CLI wiring it all together
- `adapt/utils/formatting.py` — Rich-based terminal output
- `adapt/utils/env.py` — minimal `.env` loader, no extra dependency

### Notes on the risk model

Connection risk is computed deterministically (not by the LLM) from: inbound
delay, scheduled layover, whether a terminal change is required, and an
estimated walking time — the LLM only narrates the result. This keeps risk
scoring reproducible and auditable; swap `adapt/agents/connection_risk.py`'s
formula for a real predictive model later without touching the CLI or the
orchestrator.
