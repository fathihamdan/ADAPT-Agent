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
}

export interface PassengerRouteOption {
  code: string
  route: string
  departs: string
  arrives: string
  duration_minutes: number
  layover_minutes: number | null
  connections: number
  airlines: string
  legs: PassengerRouteLeg[]
  recommended: boolean
  source: string
  price: number | null
  currency: string | null
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
