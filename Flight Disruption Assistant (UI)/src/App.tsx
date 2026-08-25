import { useState, useEffect, useCallback } from 'react'
import FrameDisruption from './components/FrameDisruption'
import FrameRiskPredictor from './components/FrameRiskPredictor'
import FrameRerouting from './components/FrameRerouting'
import PassengerSearch from './components/PassengerSearch'
import {
  fetchQueue, refreshQueue, fetchPassengerDetail, fetchLiveTrack,
  fetchSystemStatus, fetchFlights,
} from './api'
import type { FlightRecord, PassengerDetail, QueueRow, SystemStatus } from './types'

type FlightSortKey = keyof Pick<FlightRecord, 'flight_no' | 'origin' | 'destination' | 'sched_dep' | 'status' | 'delay_minutes'>
type View = 'queue' | 'flights' | 'sources' | 'passenger-search'
type DetailTab = 'disruption' | 'risk' | 'reroute'

const NAV_ITEMS: Array<{ icon: string; label: string; view: View }> = [
  { icon: '🔗', label: 'Connection Queue', view: 'queue' },
  { icon: '✈️', label: 'Flights', view: 'flights' },
  { icon: '📡', label: 'Data Sources', view: 'sources' },
  { icon: '＋', label: 'New Passenger', view: 'passenger-search' },
]

const STATUS_LABEL: Record<string, { label: string; bg: string; color: string }> = {
  DELAYED: { label: '⚠ Delayed', bg: '#FFE3DB', color: '#FF6B4A' },
  CANCELLED: { label: '✕ Cancelled', bg: '#FFE3DB', color: '#FF6B4A' },
  ON_TIME: { label: '✓ On time', bg: '#DBF7EA', color: '#1A9B65' },
  DIVERTED: { label: '⚠ Diverted', bg: '#FFE3DB', color: '#FF6B4A' },
}

const RISK_LABEL: Record<string, { bg: string; color: string }> = {
  CRITICAL: { bg: '#FFE3DB', color: '#B23434' },
  HIGH: { bg: '#FFE3DB', color: '#FF6B4A' },
  MEDIUM: { bg: '#FFF1DA', color: '#D4870A' },
  LOW: { bg: '#DBF7EA', color: '#1A9B65' },
}

export default function App() {
  const [view, setView] = useState<View>('queue')

  const [queue, setQueue] = useState<QueueRow[]>([])
  const [queueLoading, setQueueLoading] = useState(true)
  const [queueError, setQueueError] = useState<string | null>(null)
  const [queueRefreshing, setQueueRefreshing] = useState(false)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<PassengerDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailTab, setDetailTab] = useState<DetailTab>('disruption')

  const [searchQuery, setSearchQuery] = useState('')
  const [searchFailed, setSearchFailed] = useState(false)

  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null)
  const [statusChecking, setStatusChecking] = useState(false)
  const [statusCheckedAt, setStatusCheckedAt] = useState<Date | null>(null)

  const [flights, setFlights] = useState<FlightRecord[]>([])
  const [flightsError, setFlightsError] = useState<string | null>(null)
  const [disruptedOnly, setDisruptedOnly] = useState(false)
  const [sortKey, setSortKey] = useState<FlightSortKey>('sched_dep')
  const [sortDir, setSortDir] = useState<1 | -1>(1)

  // Load the connection-risk queue once, on mount.
  useEffect(() => {
    fetchQueue()
      .then(rows => {
        setQueue(rows)
        setQueueLoading(false)
      })
      .catch(err => {
        setQueueError(String(err))
        setQueueLoading(false)
      })
  }, [])

  // Manual refresh only - the backend caches passenger data after its first
  // build (including live AviationStack lookups) rather than re-fetching on
  // every page load, so this button is the only thing that triggers a fresh
  // lookup for PSG1002's real flight.
  const handleRefreshQueue = useCallback(async () => {
    setQueueRefreshing(true)
    try {
      const rows = await refreshQueue()
      setQueue(rows)
      if (selectedId) {
        const data = await fetchPassengerDetail(selectedId)
        setDetail(data)
      }
    } catch (err) {
      setQueueError(String(err))
    } finally {
      setQueueRefreshing(false)
    }
  }, [selectedId])

  const loadPassenger = useCallback((passengerId: string) => {
    setSelectedId(passengerId)
    setDetailTab('disruption')
    setDetailLoading(true)
    setDetailError(null)
    fetchPassengerDetail(passengerId)
      .then(data => {
        setDetail(data)
        setDetailLoading(false)
      })
      .catch(err => {
        setDetailError(String(err))
        setDetailLoading(false)
      })
  }, [])

  const trackLiveFlight = useCallback((flightIata: string) => {
    setSelectedId(`LIVE:${flightIata}`)
    setDetailTab('disruption')
    setSearchFailed(false)
    setDetailLoading(true)
    setDetailError(null)
    fetchLiveTrack(flightIata)
      .then(data => {
        setDetail(data)
        setDetailLoading(false)
      })
      .catch(err => {
        setSearchFailed(true)
        setDetailError(String(err))
        setDetailLoading(false)
      })
  }, [])

  const handleSearch = useCallback((raw: string) => {
    const query = raw.trim()
    if (!query) return
    const match = queue.find(
      row => row.passenger_id.toLowerCase() === query.toLowerCase()
        || row.flight_a.flight_no.toLowerCase() === query.toLowerCase()
        || row.flight_b.flight_no.toLowerCase() === query.toLowerCase()
    )
    if (match) {
      setSearchQuery('')
      loadPassenger(match.passenger_id)
    } else {
      trackLiveFlight(query.toUpperCase())
    }
  }, [queue, loadPassenger, trackLiveFlight])

  // Real data-source status - what's actually configured right now, not what the
  // code theoretically supports. Loaded once, and re-checkable via the table's
  // refresh button since a running server won't notice a .env change on its own.
  const refreshStatus = useCallback(() => {
    setStatusChecking(true)
    fetchSystemStatus()
      .then(data => {
        setSystemStatus(data)
        setStatusCheckedAt(new Date())
      })
      .catch(() => setSystemStatus(null))
      .finally(() => setStatusChecking(false))
  }, [])

  useEffect(() => {
    refreshStatus()
  }, [refreshStatus])

  // Load the flight table - the locally harvested database when it has data,
  // which is hundreds of real flights rather than the old 25-row live page.
  // Refetches when the disrupted filter changes, since that filter is applied
  // server-side against the whole database, not just the rows already loaded.
  useEffect(() => {
    setFlightsError(null)
    fetchFlights({ disrupted: disruptedOnly })
      .then(setFlights)
      .catch(err => setFlightsError(String(err)))
  }, [disruptedOnly])

  const toggleSort = useCallback((key: FlightSortKey) => {
    setSortKey(prevKey => {
      if (prevKey === key) {
        setSortDir(prevDir => (prevDir === 1 ? -1 : 1))
        return prevKey
      }
      setSortDir(1)
      return key
    })
  }, [])

  const sortedFlights = [...flights].sort((a, b) => {
    const av = a[sortKey]
    const bv = b[sortKey]
    const cmp = typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv))
    return cmp * sortDir
  })

  const criticalCount = queue.filter(r => r.risk_level === 'CRITICAL').length
  const today = new Date().toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

  return (
    <div
      className="flex min-h-screen"
      style={{ background: 'linear-gradient(135deg, #8FD3FF 0%, #EAF6FF 55%, #F7FBFF 100%)' }}
    >
      {/* Sidebar */}
      <aside
        className="flex flex-col"
        style={{
          width: 220,
          minHeight: '100vh',
          background: 'rgba(255,255,255,0.55)',
          backdropFilter: 'blur(20px)',
          borderRight: '1px solid rgba(47,143,224,0.12)',
          padding: '28px 0',
          flexShrink: 0,
        }}
      >
        {/* Logo */}
        <div className="px-6 mb-8">
          <div className="flex items-center gap-2">
            <div
              style={{
                width: 36, height: 36, borderRadius: 10,
                background: 'linear-gradient(135deg, #2F8FE0, #8FD3FF)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 18,
              }}
            >✈️</div>
            <div>
              <div className="font-display font-bold" style={{ fontSize: 16, color: '#1B2A41', lineHeight: 1.1 }}>GateWatch</div>
              <div className="font-mono" style={{ fontSize: 9, color: '#5B6B84', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Ops Desk</div>
            </div>
          </div>
        </div>

        {/* Nav - actually switches the visible section now, instead of every
            section being permanently stacked on one long page. */}
        <nav className="flex flex-col gap-1 px-3 flex-1">
          {NAV_ITEMS.map(item => {
            const isActive = view === item.view
            return (
              <button
                key={item.label}
                onClick={() => setView(item.view)}
                className="flex items-center gap-3 text-left rounded-xl px-3 py-2.5 transition-all"
                style={{
                  background: isActive ? 'linear-gradient(135deg, rgba(47,143,224,0.12), rgba(143,211,255,0.10))' : 'transparent',
                  border: isActive ? '1px solid rgba(47,143,224,0.18)' : '1px solid transparent',
                  color: isActive ? '#1B6FC2' : '#5B6B84',
                  fontFamily: 'Inter, sans-serif',
                  fontWeight: isActive ? 600 : 400,
                  fontSize: 14,
                  cursor: 'pointer',
                }}
              >
                <span style={{ fontSize: 16 }}>{item.icon}</span>
                <span style={{ flex: 1 }}>{item.label}</span>
              </button>
            )
          })}
        </nav>

        {/* Queue summary - this is a triage tool, so the persistent context is
            "how bad is the queue", not any one passenger's identity. */}
        <div className="px-4 mt-4 pt-4" style={{ borderTop: '1px solid rgba(47,143,224,0.1)' }}>
          <div className="font-mono" style={{ fontSize: 10, color: '#5B6B84', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            {today}
          </div>
          <div className="font-display font-bold" style={{ fontSize: 22, color: criticalCount ? '#B23434' : '#1B2A41', marginTop: 2 }}>
            {criticalCount} critical
          </div>
          <div className="font-body" style={{ fontSize: 12, color: '#5B6B84' }}>
            of {queue.length} self-connect booking{queue.length !== 1 ? 's' : ''} watched
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex flex-col gap-6 p-6 min-h-screen" style={{ flex: 1, minWidth: 0 }}>

      {view === 'queue' && (
      <>
        {/* Header: title + real-flight search */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="font-display font-bold" style={{ fontSize: 22, color: '#1B2A41' }}>Connection Risk Queue</h1>
            <p className="font-body" style={{ fontSize: 13, color: '#5B6B84', marginTop: 2 }}>
              Self-connect bookings across different airlines - sorted worst-first
            </p>
          </div>
          <div>
            <input
              type="text"
              value={searchQuery}
              onChange={e => { setSearchQuery(e.target.value); setSearchFailed(false) }}
              onKeyDown={e => { if (e.key === 'Enter') handleSearch(searchQuery) }}
              placeholder="Look up any real flight (e.g. AA100)"
              className="font-body"
              style={{
                width: 280, padding: '10px 14px', borderRadius: 12,
                border: searchFailed ? '1.5px solid #FF6B4A' : '1.5px solid rgba(47,143,224,0.15)',
                background: 'rgba(255,255,255,0.7)', fontSize: 13, color: '#1B2A41', outline: 'none',
              }}
            />
            {searchFailed && (
              <p className="font-body" style={{ fontSize: 11, color: '#FF6B4A', marginTop: 4 }}>
                No match in the queue or live AviationStack data.
              </p>
            )}
          </div>
        </div>

        {/* Queue table */}
        <div
          style={{
            background: 'rgba(255,255,255,0.7)', border: '1px solid rgba(47,143,224,0.10)',
            borderRadius: 20, padding: '18px 22px',
          }}
        >
          <div className="flex items-center justify-between mb-3">
            <p className="font-body" style={{ fontSize: 12, color: '#5B6B84' }}>Click a row for full details</p>
            <button
              onClick={handleRefreshQueue}
              disabled={queueRefreshing}
              title="Re-check live flight data for PSG1002 (cached otherwise)"
              className="font-body font-semibold"
              style={{
                fontSize: 12, color: '#1B6FC2', background: 'rgba(47,143,224,0.10)',
                border: '1px solid rgba(47,143,224,0.18)', borderRadius: 999,
                padding: '6px 14px', cursor: queueRefreshing ? 'default' : 'pointer',
                opacity: queueRefreshing ? 0.6 : 1,
              }}
            >
              {queueRefreshing ? 'Refreshing…' : '⟳ Refresh'}
            </button>
          </div>

          {queueError && (
            <p className="font-body" style={{ fontSize: 12, color: '#FF6B4A', marginBottom: 8 }}>{queueError}</p>
          )}

          <div style={{ overflowX: 'auto' }}>
            <table className="w-full" style={{ borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(47,143,224,0.12)' }}>
                  {['Passenger', 'Flight A', 'Flight B', 'Connection', 'Risk'].map(h => (
                    <th
                      key={h}
                      className="font-mono"
                      style={{
                        textAlign: 'left', fontSize: 10, color: '#8A9BB5', textTransform: 'uppercase',
                        letterSpacing: '0.06em', padding: '0 12px 10px', fontWeight: 600,
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {queueLoading ? (
                  <tr><td colSpan={5} className="font-body" style={{ fontSize: 12, color: '#8A9BB5', padding: '16px 12px', textAlign: 'center' }}>Loading queue…</td></tr>
                ) : queue.length ? (
                  queue.map(row => {
                    const risk = RISK_LABEL[row.risk_level] ?? RISK_LABEL.LOW
                    const isSelected = row.passenger_id === selectedId
                    return (
                      <tr
                        key={row.passenger_id}
                        onClick={() => loadPassenger(row.passenger_id)}
                        className="hover:bg-[rgba(47,143,224,0.05)]"
                        style={{
                          borderBottom: '1px solid rgba(47,143,224,0.06)', transition: 'background 0.12s',
                          cursor: 'pointer', background: isSelected ? 'rgba(47,143,224,0.07)' : undefined,
                        }}
                      >
                        <td style={{ padding: '10px 12px' }}>
                          <div className="font-body font-semibold" style={{ fontSize: 13, color: '#1B2A41' }}>{row.name}</div>
                          <div className="font-mono" style={{ fontSize: 10, color: '#8A9BB5' }}>{row.passenger_id}</div>
                        </td>
                        <td className="font-mono" style={{ fontSize: 12, color: '#5B6B84', padding: '10px 12px' }}>
                          {row.flight_a.flight_no}
                          <div style={{ fontSize: 10, color: '#8A9BB5' }}>{row.flight_a.airline} · {row.flight_a.route}</div>
                        </td>
                        <td className="font-mono" style={{ fontSize: 12, color: '#5B6B84', padding: '10px 12px' }}>
                          {row.flight_b.flight_no}
                          <div style={{ fontSize: 10, color: '#8A9BB5' }}>{row.flight_b.airline} · {row.flight_b.route}</div>
                        </td>
                        <td className="font-mono" style={{ fontSize: 12, color: '#5B6B84', padding: '10px 12px' }}>{row.connection_airport}</td>
                        <td style={{ padding: '10px 12px' }}>
                          <span
                            className="font-mono font-bold"
                            style={{
                              fontSize: 10, letterSpacing: '0.04em', textTransform: 'uppercase',
                              padding: '3px 9px', borderRadius: 999,
                              color: risk.color, background: risk.bg,
                            }}
                          >
                            {row.risk_level} · {row.risk_pct}%
                          </span>
                        </td>
                      </tr>
                    )
                  })
                ) : (
                  <tr><td colSpan={5} className="font-body" style={{ fontSize: 12, color: '#8A9BB5', padding: '16px 12px', textAlign: 'center' }}>No self-connect bookings to watch right now.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Detail panel - tabbed so only one section is visible at a time */}
        {selectedId && (
          <div className="flex flex-col gap-4">
            {detailLoading || !detail ? (
              <div
                style={{
                  background: 'rgba(255,255,255,0.7)', border: '1px solid rgba(47,143,224,0.10)',
                  borderRadius: 20, padding: '24px', textAlign: 'center',
                }}
              >
                {detailError ? (
                  <p className="font-body" style={{ color: '#B23434', fontSize: 13 }}>{detailError}</p>
                ) : (
                  <p className="font-body" style={{ color: '#5B6B84', fontSize: 13 }}>Loading passenger detail…</p>
                )}
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <h2 className="font-display font-bold" style={{ fontSize: 18, color: '#1B2A41' }}>
                    {detail.name} <span className="font-mono" style={{ fontSize: 12, color: '#8A9BB5', fontWeight: 400 }}>({detail.passenger_id})</span>
                  </h2>
                  <button
                    onClick={() => { setSelectedId(null); setDetail(null) }}
                    className="font-body"
                    style={{ fontSize: 12, color: '#5B6B84', background: 'none', border: 'none', cursor: 'pointer' }}
                  >
                    ✕ Close
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  {([
                    ['disruption', 'Disruption'],
                    ['risk', 'Connection Risk'],
                    ['reroute', 'Rerouting'],
                  ] as [DetailTab, string][]).map(([tab, label]) => (
                    <button
                      key={tab}
                      onClick={() => setDetailTab(tab)}
                      className="font-body font-semibold"
                      style={{
                        fontSize: 12, padding: '7px 16px', borderRadius: 999, cursor: 'pointer',
                        border: detailTab === tab ? '1px solid rgba(47,143,224,0.30)' : '1px solid rgba(47,143,224,0.10)',
                        color: detailTab === tab ? '#1B6FC2' : '#5B6B84',
                        background: detailTab === tab ? 'rgba(47,143,224,0.10)' : 'rgba(255,255,255,0.7)',
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>

                <div
                  style={{
                    background: '#ffffff', borderRadius: 24,
                    boxShadow: '0 12px 40px rgba(47,143,224,0.10)', overflow: 'hidden',
                  }}
                >
                  {detailTab === 'disruption' && (
                    <FrameDisruption disruption={detail.disruption} onNext={() => setDetailTab('risk')} />
                  )}
                  {detailTab === 'risk' && (
                    <FrameRiskPredictor connection={detail.connection} active onNext={() => setDetailTab('reroute')} />
                  )}
                  {detailTab === 'reroute' && (
                    <FrameRerouting reroute={detail.reroute} active onNext={() => setDetailTab('disruption')} />
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </>
      )}

      {view === 'sources' && (
        <div
          style={{
            background: 'rgba(255,255,255,0.7)', border: '1px solid rgba(47,143,224,0.10)',
            borderRadius: 20, padding: '18px 22px',
          }}
        >
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="font-display font-bold" style={{ fontSize: 16, color: '#1B2A41' }}>Data Sources</h3>
              <p className="font-body" style={{ fontSize: 12, color: '#5B6B84' }}>
                What&apos;s actually powering this session right now
              </p>
            </div>
            <div className="flex items-center gap-3">
              {statusCheckedAt && (
                <span className="font-mono" style={{ fontSize: 10, color: '#8A9BB5' }}>
                  Checked {statusCheckedAt.toLocaleTimeString()}
                </span>
              )}
              <button
                onClick={refreshStatus}
                disabled={statusChecking}
                className="font-body font-semibold"
                style={{
                  fontSize: 12, color: '#1B6FC2', background: 'rgba(47,143,224,0.10)',
                  border: '1px solid rgba(47,143,224,0.18)', borderRadius: 999,
                  padding: '6px 14px', cursor: statusChecking ? 'default' : 'pointer',
                  opacity: statusChecking ? 0.6 : 1,
                }}
              >
                {statusChecking ? 'Checking…' : '⟳ Refresh'}
              </button>
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table className="w-full" style={{ borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(47,143,224,0.12)' }}>
                  {['Feature', 'Status', 'Backend', 'Powers'].map(h => (
                    <th
                      key={h}
                      className="font-mono"
                      style={{
                        textAlign: 'left', fontSize: 10, color: '#8A9BB5', textTransform: 'uppercase',
                        letterSpacing: '0.06em', padding: '0 12px 10px', fontWeight: 600,
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {systemStatus ? (
                  [
                    { label: 'AI Explanations', status: systemStatus.llm, powers: 'Disruption Explainer, Connection Risk, Rerouting narratives' },
                    { label: 'Rerouting Search', status: systemStatus.rerouting, powers: 'Rerouting Recommender alternatives' },
                    { label: 'Live Flight Tracking', status: systemStatus.live_tracking, powers: 'Search box real-flight lookup, PSG1002/PSG1003 live legs' },
                  ].map(row => (
                    <tr
                      key={row.label}
                      className="hover:bg-[rgba(47,143,224,0.05)]"
                      style={{ borderBottom: '1px solid rgba(47,143,224,0.06)', transition: 'background 0.12s' }}
                    >
                      <td className="font-body font-semibold" style={{ fontSize: 13, color: '#1B2A41', padding: '10px 12px' }}>
                        {row.label}
                      </td>
                      <td style={{ padding: '10px 12px' }}>
                        <span
                          className="font-mono font-bold"
                          style={{
                            fontSize: 10, letterSpacing: '0.04em', textTransform: 'uppercase',
                            padding: '3px 9px', borderRadius: 999, display: 'inline-flex', alignItems: 'center', gap: 5,
                            color: row.status.is_live ? '#1A9B65' : '#8A9BB5',
                            background: row.status.is_live ? '#DBF7EA' : '#F1F5FB',
                          }}
                        >
                          <span style={{
                            width: 6, height: 6, borderRadius: '50%',
                            background: row.status.is_live ? '#2ECC87' : '#CBD5E1',
                          }} />
                          {row.status.is_live ? 'Live' : 'Mock'}
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: 11, color: '#5B6B84', padding: '10px 12px' }}>
                        {'name' in row.status ? row.status.name : row.status.source}
                      </td>
                      <td className="font-body" style={{ fontSize: 11, color: '#8A9BB5', padding: '10px 12px' }}>
                        {row.powers}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="font-body" style={{ fontSize: 12, color: '#8A9BB5', padding: '16px 12px', textAlign: 'center' }}>
                      Checking backend status…
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {view === 'passenger-search' && <PassengerSearch />}

      {view === 'flights' && (
        <div
          style={{
            background: 'rgba(255,255,255,0.7)', border: '1px solid rgba(47,143,224,0.10)',
            borderRadius: 20, padding: '18px 22px',
          }}
        >
          <div className="mb-3 flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h3 className="font-display font-bold" style={{ fontSize: 16, color: '#1B2A41' }}>Flights</h3>
              {/* Report whatever the backend actually served rather than guessing
                  from a hardcoded string - the source can be the local harvested
                  DB, the live API, a cached response, or mock data. */}
              <p className="font-body" style={{ fontSize: 12, color: '#5B6B84' }}>
                {flights.length} flight{flights.length === 1 ? '' : 's'}
                {flights[0]?.source ? ` · ${flights[0].source}` : ''}
                {' · '}click a column to sort
              </p>
            </div>
            <button
              onClick={() => setDisruptedOnly(v => !v)}
              className="font-body font-semibold"
              style={{
                fontSize: 12, borderRadius: 999, padding: '6px 14px', cursor: 'pointer',
                color: disruptedOnly ? '#C2410C' : '#5B6B84',
                background: disruptedOnly ? 'rgba(255,107,74,0.12)' : 'rgba(255,255,255,0.7)',
                border: disruptedOnly ? '1px solid rgba(255,107,74,0.35)' : '1px solid rgba(47,143,224,0.18)',
              }}
            >
              {disruptedOnly ? '● Disrupted only' : '○ Disrupted only'}
            </button>
          </div>

          {flightsError && (
            <p className="font-body" style={{ fontSize: 12, color: '#FF6B4A', marginBottom: 8 }}>{flightsError}</p>
          )}

          <div style={{ overflowX: 'auto' }}>
            <table className="w-full" style={{ borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(47,143,224,0.12)' }}>
                  {([
                    ['flight_no', 'Flight'],
                    ['origin', 'From'],
                    ['destination', 'To'],
                    ['sched_dep', 'Departs'],
                    ['status', 'Status'],
                    ['delay_minutes', 'Delay'],
                  ] as [FlightSortKey, string][]).map(([key, label]) => (
                    <th
                      key={key}
                      onClick={() => toggleSort(key)}
                      className="font-mono"
                      style={{
                        textAlign: 'left', fontSize: 10, color: sortKey === key ? '#1B6FC2' : '#8A9BB5',
                        textTransform: 'uppercase', letterSpacing: '0.06em', padding: '0 12px 10px',
                        fontWeight: 600, cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
                      }}
                    >
                      {label}{sortKey === key ? (sortDir === 1 ? ' ▲' : ' ▼') : ''}
                    </th>
                  ))}
                  <th className="font-mono" style={{ textAlign: 'left', fontSize: 10, color: '#8A9BB5', textTransform: 'uppercase', letterSpacing: '0.06em', padding: '0 12px 10px', fontWeight: 600 }}>
                    Gate
                  </th>
                  <th className="font-mono" style={{ textAlign: 'left', fontSize: 10, color: '#8A9BB5', textTransform: 'uppercase', letterSpacing: '0.06em', padding: '0 12px 10px', fontWeight: 600 }}>
                    Source
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedFlights.length ? (
                  sortedFlights.map(f => (
                    // Real flight numbers aren't unique (codeshares, different real
                    // flights reusing a number) - keying on flight_no alone caused
                    // React to misattribute rows on sort. This composite key is
                    // actually unique per row.
                    <tr
                      key={`${f.flight_no}-${f.origin}-${f.sched_dep}`}
                      className="hover:bg-[rgba(47,143,224,0.05)]"
                      style={{ borderBottom: '1px solid rgba(47,143,224,0.06)', transition: 'background 0.12s' }}
                    >
                      <td className="font-mono font-bold" style={{ fontSize: 12, color: '#1B2A41', padding: '9px 12px' }}>{f.flight_no}</td>
                      <td className="font-mono" style={{ fontSize: 12, color: '#5B6B84', padding: '9px 12px' }}>{f.origin}</td>
                      <td className="font-mono" style={{ fontSize: 12, color: '#5B6B84', padding: '9px 12px' }}>{f.destination}</td>
                      <td className="font-mono" style={{ fontSize: 12, color: '#5B6B84', padding: '9px 12px' }}>{f.sched_dep}</td>
                      <td style={{ padding: '9px 12px' }}>
                        <span
                          className="font-mono font-bold"
                          style={{
                            fontSize: 10, letterSpacing: '0.04em', textTransform: 'uppercase',
                            padding: '3px 9px', borderRadius: 999,
                            color: (STATUS_LABEL[f.status] ?? STATUS_LABEL.ON_TIME).color,
                            background: (STATUS_LABEL[f.status] ?? STATUS_LABEL.ON_TIME).bg,
                          }}
                        >
                          {f.status}
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: 12, color: f.delay_minutes > 0 ? '#FF6B4A' : '#8A9BB5', padding: '9px 12px' }}>
                        {f.delay_minutes > 0 ? `+${f.delay_minutes}m` : '–'}
                      </td>
                      <td className="font-mono" style={{ fontSize: 12, color: '#5B6B84', padding: '9px 12px' }}>{f.gate || '–'}</td>
                      <td style={{ padding: '9px 12px' }}>
                        <span
                          className="font-mono"
                          style={{
                            fontSize: 9, letterSpacing: '0.04em', textTransform: 'uppercase',
                            padding: '2px 8px', borderRadius: 999,
                            color: f.source.includes('live') ? '#1A9B65' : '#8A9BB5',
                            background: f.source.includes('live') ? '#DBF7EA' : '#F1F5FB',
                          }}
                        >
                          {f.source.includes('live') ? 'Live' : 'Mock'}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={8} className="font-body" style={{ fontSize: 12, color: '#8A9BB5', padding: '16px 12px', textAlign: 'center' }}>
                      {flightsError ? 'Could not load flights.' : 'Loading flights…'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
      </main>
    </div>
  )
}
