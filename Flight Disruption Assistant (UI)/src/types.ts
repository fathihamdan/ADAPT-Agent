export interface SystemStatus {
  llm: { name: string; is_live: boolean }
  rerouting: { source: string; is_live: boolean }
  live_tracking: { source: string; is_live: boolean }
}

export interface FlightRecord {
  flight_no: string
  airline: string
  origin: string
  destination: string
  sched_dep: string
  sched_arr: string
  terminal_dep: string
  terminal_arr: string
  status: 'ON_TIME' | 'DELAYED' | 'CANCELLED' | 'DIVERTED'
  delay_minutes: number
  cause: string
  gate: string
  source: string
}

export interface QueueFlightRef {
  flight_no: string
  airline: string
  route: string
  status: 'ON_TIME' | 'DELAYED' | 'CANCELLED' | 'DIVERTED'
}

export interface QueueRow {
  passenger_id: string
  name: string
  flight_a: QueueFlightRef
  flight_b: QueueFlightRef
  connection_airport: string
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  risk_pct: number
}

export interface Disruption {
  flight_no: string
  origin: string
  origin_city: string
  destination: string
  destination_city: string
  status: string
  cause: string
  delay_minutes: number
  raw_feed: string
  ai_html: string
}

export type StepStatus = 'on' | 'warn'
export type Step = [label: string, time: string, status: StepStatus]

export interface Connection {
  from: string
  to: string
  risk_pct: number
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  risk_band_class: string
  available_min: number
  required_min: number
  buffer_min: number
  next_gate: string
  ai_text: string
  factors: string[]
  steps: Step[]
}

export interface RerouteOption {
  code: string
  route: string
  depart: string
  arrival: string
  delay_vs_original: number
  connections: number
  recommended: boolean
}

export interface Reroute {
  reason: string
  narrative: string
  options: RerouteOption[]
}

export interface ReroutedPassenger {
  passenger_id: string
  name: string
  /** What the risk was before the desk acted - what this reroute prevented. */
  original_risk: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | null
  original_risk_pct: number | null
  connection_airport: string | null
  option_code: string | null
  option_route: string | null
  option_departs: string | null
  option_arrives: string | null
  delay_vs_original: number | null
  connections: number | null
  rerouted_at: number
  rerouted_age_seconds: number
}

export interface FlightRefreshResult {
  ok: boolean
  error: string | null
  /** Flights that were not already in the database. */
  added: number
  /** Known flights whose status was refreshed - not duplicates. */
  updated: number
  api_calls?: number
  total: number
}

export interface AirportInfo {
  code: string
  name: string
  city: string
}

export interface PassengerRouteLeg {
  flight_no: string
  airline: string
  origin: string
  destination: string
  departs: string
  arrives: string
  /** Transit gap after this leg; null on the final leg. */
  layover_after_minutes: number | null
  /** Gap is shorter than the minimum connection buffer. */
  layover_tight: boolean
  /** The gap where the passenger changes ticket - a delay here strands them. */
  self_transfer_after: boolean
}

export interface PassengerRouteOption {
  code: string
  route: string
  departs: string
  arrives: string
  duration_minutes: number
  /** Total time on the ground across all stops; null for a nonstop. */
  layover_minutes: number | null
  layover_airports: string[]
  tight_connection: boolean
  /** Final leg's arrival airport - Atlas may answer with a nearby metro airport. */
  arrives_at: string
  destination_mismatch: boolean
  connections: number
  airlines: string
  legs: PassengerRouteLeg[]
  recommended: boolean
  source: string
  price: number | null
  currency: string | null
  /** Two independent Atlas tickets stitched together - no airline protection. */
  self_transfer: boolean
  ticket_count: number
  /** Airport where the ticket changes hands; null unless self_transfer. */
  transfer_airport: string | null
}

export interface PassengerRouteSearchResult {
  passenger_name: string
  origin: string
  destination: string
  departure: string
  narrative: string
  narrative_html: string
  options: PassengerRouteOption[]
}

export interface PassengerDetail {
  passenger_id: string
  name: string
  flights: Array<{
    flight_no: string
    airline: string
    origin: string
    destination: string
    sched_dep: string
    sched_arr: string
    status: string
    delay_minutes: number
  }>
  disruption: Disruption | null
  connection: Connection | null
  reroute: Reroute | null
}
