import type { AirportInfo, FlightRecord, PassengerDetail, PassengerRouteSearchResult, QueueRow, SystemStatus } from './types'

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
