import type {
  AirportInfo, FlightRecord, PassengerDetail, PassengerRouteSearchResult,
  QueueRow, ReroutedPassenger, RerouteOption, FlightRefreshResult, SystemStatus,
} from './types'

async function extractErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    // response wasn't JSON - fall through to the generic message
  }
  return fallback
}

export async function fetchSystemStatus(): Promise<SystemStatus> {
  const res = await fetch('/api/status')
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res, `Failed to load system status (${res.status})`))
  }
  return res.json()
}

export async function fetchFlights(options: {
  limit?: number
  disrupted?: boolean
} = {}): Promise<FlightRecord[]> {
  // The locally harvested database holds hundreds of real flights, so ask for a
  // whole table rather than the handful a single live API page used to return.
  const params = new URLSearchParams({ limit: String(options.limit ?? 500) })
  if (options.disrupted) params.set('disrupted', 'true')

  const res = await fetch(`/api/flights?${params}`)
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res, `Failed to load flights (${res.status})`))
  }
  return res.json()
}

export async function confirmReroute(
  passengerId: string,
  option: RerouteOption,
): Promise<{ passenger_id: string; name: string }> {
  const res = await fetch(`/api/queue/${passengerId}/reroute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      code: option.code,
      route: option.route,
      depart: option.depart,
      arrival: option.arrival,
      delay_vs_original: option.delay_vs_original,
      connections: option.connections,
    }),
  })
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res, `Failed to confirm reroute (${res.status})`))
  }
  return res.json()
}

export async function fetchReroutedPassengers(): Promise<ReroutedPassenger[]> {
  const res = await fetch('/api/rerouted')
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res, `Failed to load rerouted passengers (${res.status})`))
  }
  return res.json()
}

export async function undoReroute(passengerId: string): Promise<void> {
  const res = await fetch(`/api/rerouted/${passengerId}`, { method: 'DELETE' })
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res, `Failed to restore passenger (${res.status})`))
  }
}

/** Pull the newest flights into the local database. Costs API quota, so this is
 *  only ever triggered by an explicit button press. */
export async function refreshFlightDatabase(pages = 3): Promise<FlightRefreshResult> {
  const res = await fetch(`/api/flights/refresh?pages=${pages}`, { method: 'POST' })
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res, `Failed to refresh flights (${res.status})`))
  }
  return res.json()
}

export async function fetchQueue(): Promise<QueueRow[]> {
  const res = await fetch('/api/queue')
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res, `Failed to load queue (${res.status})`))
  }
  return res.json()
}

export async function refreshQueue(): Promise<QueueRow[]> {
  const res = await fetch('/api/queue/refresh', { method: 'POST' })
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res, `Failed to refresh queue (${res.status})`))
  }
  return res.json()
}

export async function fetchPassengerDetail(passengerId: string): Promise<PassengerDetail> {
  const res = await fetch(`/api/queue/${passengerId}`)
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res, `Failed to load passenger ${passengerId} (${res.status})`))
  }
  return res.json()
}

export async function fetchLiveTrack(flightIata: string): Promise<PassengerDetail> {
  const res = await fetch(`/api/track/${flightIata}`)
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res, `No live data found for flight ${flightIata} (${res.status})`))
  }
  return res.json()
}

export async function fetchAirports(): Promise<AirportInfo[]> {
  const res = await fetch('/api/airports')
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res, `Failed to load airports (${res.status})`))
  }
  return res.json()
}

export async function searchPassengerRoutes(request: {
  passenger_name: string
  origin: string
  destination: string
  departure: string
}): Promise<PassengerRouteSearchResult> {
  const res = await fetch('/api/passenger-search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res, `Failed to search routes (${res.status})`))
  }
  return res.json()
}
