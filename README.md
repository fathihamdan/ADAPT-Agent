# ADAPT-Agent
## Airline Disruption Analysis &amp; Prevention Technology  
An Agentic AI-Powered system 

Self-connect trips — flight A on one airline, flight B on a different one, sold as a single journey by a 3rd-party ticket dealer — are a liability nobody but the dealer is watching. Neither airline protects that connection if flight A runs late; they don't even know the other flight exists. ADAPT-Agent (Airline Disruption Analysis & Prevention Technology) is an agentic AI tool for that dealer's **ops desk**: it watches every customer's self-connect booking, explains what's going wrong in plain English, predicts the real probability of a missed connection, and finds a rerouting option before the customer ever reaches the gate.

## How ADAPT Revolutionizes Disruption Ops:
ADAPT offers an end-to-end autonomous disruption management experience through its intelligent features and automated actions:

**- Disruption Explainer:** No more deciphering cryptic airline announcements. ADAPT translates complex technical information regarding delays, cancellations, weather events, and Air Traffic Control (ATC) issues into clear, easy-to-understand explanations for the ops desk. Know exactly what's happening and why, for every passenger in the queue.

**- Connection Risk Predictor:** For every passenger who self-connected two separately-ticketed flights, ADAPT detects the real connection and calculates the precise probability of missing it. It intelligently analyzes critical factors such as layover duration, terminal distances, and estimated walking times, providing real-time risk assessments — sorted worst-first.

**- Rerouting Connection:** When disruptions strike, ADAPT acts swiftly. Our system proactively identifies and recommends optimal alternative flights and routes, presenting the ops desk with the best options to protect the customer's trip.

**- Rescheduling & Rebooking Agent:** Recommending an alternative is only half the job — ADAPT carries it through to a ticket. Backed by the Atlas Flight API, the agent **discovers** live bookable inventory, **verifies** the real fare before committing, offers **ancillaries** (baggage and seats), then completes **booking, payment and ticketing** — pausing for the ops desk's explicit approval at every step that costs money. See [Autonomous rebooking via the Atlas Flight API](#autonomous-rebooking-via-the-atlas-flight-api).

## CLI Prototype

This repo currently ships the CLI-first prototype (a web UI follows the same data,
in `Flight Disruption Assistant (UI)/`). It runs fully offline out of the box
(rule-based explanations, no API key needed) and drops in real model-generated
explanations the moment you set `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY`.

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

(Or set `OPENROUTER_API_KEY` to route through OpenRouter instead — see `adapt/llm/openrouter_client.py`.)

Any of these can instead go in a `.env` file at the project root (`KEY=value`,
one per line). `adapt/utils/env.py` loads it on every CLI run, and `.env` is
gitignored.

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

- `adapt/models.py` — domain types (`Flight`, `Passenger`, `ConnectionRisk`, `RerouteOption`). A `Passenger` owns a flat list of booked flights — not pre-paired, not pre-ordered, and not tied to one airline's PNR
- `adapt/agents/connections.py` — `find_connections()`: detects which of a passenger's flights actually connect (same airport, chronologically valid), so nothing has to pre-declare a pairing
- `adapt/data/mock_data.py` — mock flight schedule & self-connect passengers (swap for a real flight-data / booking-dealer API later)
- `adapt/llm/` — pluggable LLM backend: `MockLLMClient` (offline, default), `AnthropicClient`, or `OpenRouterClient`; all three implement the same `LLMClient` interface and speak in ops-desk phrasing ("the passenger", not "you")
- `adapt/agents/` — the four capabilities (`disruption_explainer`, `connection_risk`, `rerouting`, `rebooking`) plus `orchestrator.py`, the agentic layer: given a passenger, it detects connections and decides autonomously which to run and in what order
- `adapt/atlas/`, `adapt/atlas_tools.py` — the Atlas Flight API client and CLI-facing tool wrappers backing live rerouting search and the rebooking agent
- `adapt/cli.py` — Typer CLI wiring it all together
- `adapt/utils/formatting.py` — Rich-based terminal output
- `adapt/utils/env.py` — minimal `.env` loader, no extra dependency
- `web/` — FastAPI backend serving the same agents as a JSON API (`/api/queue` for the triage list, `/api/queue/{passenger_id}` for detail) plus the built React ops dashboard

### Notes on the risk model

Connection risk is computed deterministically (not by the LLM) from: inbound
delay, scheduled layover, whether a terminal change is required, and an
estimated walking time — the LLM only narrates the result. This keeps risk
scoring reproducible and auditable; swap `adapt/agents/connection_risk.py`'s
formula for a real predictive model later without touching the CLI, the API,
or the orchestrator.
