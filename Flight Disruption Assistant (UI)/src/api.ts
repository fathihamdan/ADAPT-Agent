import type { FlightRecord, PassengerDetail, QueueRow, SystemStatus } from './types'

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

export async function fetchFlights(): Promise<FlightRecord[]> {
  const res = await fetch('/api/flights')
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
