import { useEffect, useState } from 'react'
import { fetchAirports, searchPassengerRoutes } from '../api'
import { AirportCombobox } from './ui/AirportCombobox'
import { ChatBubble } from './ui/ChatBubble'
import type { AirportInfo, PassengerRouteOption, PassengerRouteSearchResult } from '../types'

function defaultDeparture() {
  const now = new Date()
  now.setHours(6, 0, 0, 0)
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

function formatDuration(minutes: number) {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m`
}

/** 'Direct', '1 stop via BLR', '2 stops via BLR, DXB'. */
function describeStops(option: PassengerRouteOption) {
  if (option.connections === 0) return 'Direct'
  const label = `${option.connections} stop${option.connections === 1 ? '' : 's'}`
  return option.layover_airports.length
    ? `${label} via ${option.layover_airports.join(', ')}`
    : label
}

const FIELD_LABEL = 'font-mono'
const fieldLabelStyle: React.CSSProperties = {
  fontSize: 10,
  color: '#5B6B84',
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
}
const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '11px 13px',
  borderRadius: 10,
  border: '1px solid rgba(47,143,224,0.18)',
  background: '#fff',
  color: '#1B2A41',
  outline: 'none',
  fontSize: 13,
}

export default function PassengerSearch() {
  const [airports, setAirports] = useState<AirportInfo[]>([])
  const [airportsError, setAirportsError] = useState<string | null>(null)

  const [passengerName, setPassengerName] = useState('')
  const [origin, setOrigin] = useState('ORD')
  const [destination, setDestination] = useState('LAX')
  const [departure, setDeparture] = useState(defaultDeparture)

  const [result, setResult] = useState<PassengerRouteSearchResult | null>(null)
  const [selected, setSelected] = useState<PassengerRouteOption | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchAirports()
      .then(setAirports)
      .catch(err => setAirportsError(String(err)))
  }, [])

  const sameAirport = origin !== '' && origin === destination

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (sameAirport) {
      setError('Origin and destination must be different airports.')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)
    setSelected(null)
    try {
      const data = await searchPassengerRoutes({
        passenger_name: passengerName,
        origin,
        destination,
        departure: new Date(departure).toISOString(),
      })
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  function swapAirports() {
    setOrigin(destination)
    setDestination(origin)
  }

  function resetSearch() {
    setResult(null)
    setSelected(null)
    setError(null)
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display font-bold" style={{ fontSize: 22, color: '#1B2A41' }}>
          Find a flight for a passenger
        </h1>
        <p className="font-body" style={{ fontSize: 13, color: '#5B6B84', marginTop: 2 }}>
          The route agent ranks the best three options for your client to choose from.
        </p>
      </div>

      {airportsError && (
        <div className="font-body" style={{ color: '#B23434', background: '#FFE3DB', borderRadius: 12, padding: 13, fontSize: 13 }}>
          Could not load the airport list from the backend: {airportsError}
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        style={{ background: 'rgba(255,255,255,0.78)', border: '1px solid rgba(47,143,224,0.12)', borderRadius: 20, padding: 22 }}
      >
        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1">
            <span className={FIELD_LABEL} style={fieldLabelStyle}>Passenger name</span>
            <input
              required
              value={passengerName}
              onChange={event => setPassengerName(event.target.value)}
              placeholder="e.g. Alex Morgan"
              maxLength={120}
              className="font-body"
              style={inputStyle}
            />
          </label>

          <div className="flex items-end gap-2 flex-wrap">
            <AirportCombobox
              id="origin-airport"
              label="Origin airport"
              airports={airports}
              value={origin}
              onChange={setOrigin}
            />
            <button
              type="button"
              onClick={swapAirports}
              title="Swap origin and destination"
              className="font-body"
              style={{
                padding: '10px 13px', borderRadius: 10, cursor: 'pointer',
                border: '1px solid rgba(47,143,224,0.18)', background: '#fff',
                color: '#1B6FC2', fontSize: 14, lineHeight: 1,
              }}
            >
              ⇄
            </button>
            <AirportCombobox
              id="destination-airport"
              label="Destination airport"
              airports={airports}
              value={destination}
              onChange={setDestination}
            />
          </div>

          {sameAirport && (
            <p className="font-body" style={{ fontSize: 11, color: '#FF6B4A', marginTop: -8 }}>
              Origin and destination must be different airports.
            </p>
          )}

          <label className="flex flex-col gap-1" style={{ maxWidth: 280 }}>
            <span className={FIELD_LABEL} style={fieldLabelStyle}>Earliest departure</span>
            <input
              required
              type="datetime-local"
              value={departure}
              onChange={event => setDeparture(event.target.value)}
              className="font-body"
              style={inputStyle}
            />
          </label>
        </div>

        <div className="mt-5 flex items-center gap-3 flex-wrap">
          <button
            type="submit"
            disabled={loading || airports.length === 0 || !origin || !destination || sameAirport}
            className="font-body font-semibold"
            style={{
              padding: '10px 17px', border: 0, borderRadius: 999, background: '#2F8FE0', color: '#fff',
              cursor: loading || airports.length === 0 || !origin || !destination || sameAirport ? 'default' : 'pointer',
              opacity: loading || airports.length === 0 || !origin || !destination || sameAirport ? 0.65 : 1,
            }}
          >
            {loading ? 'Finding routes…' : 'Find best routes →'}
          </button>
          <span className="font-body" style={{ fontSize: 11, color: '#8A9BB5' }}>
            No booking is made until you choose an option.
          </span>
        </div>
      </form>

      {error && (
        <div className="font-body" style={{ color: '#B23434', background: '#FFE3DB', borderRadius: 12, padding: 13, fontSize: 13 }}>
          {error}
        </div>
      )}

      {loading && (
        <div className="flex flex-col gap-3">
          {[0, 1, 2].map(i => (
            <div
              key={i}
              style={{
                height: 96, borderRadius: 16, background: 'rgba(255,255,255,0.7)',
                border: '1px solid rgba(47,143,224,0.10)',
                animation: `skeletonPulse 1.2s ease-in-out ${i * 0.15}s infinite`,
              }}
            />
          ))}
        </div>
      )}

      {result && !loading && (
        <section className="flex flex-col gap-4 animate-fade-in">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <h2 className="font-display font-bold" style={{ fontSize: 18, color: '#1B2A41' }}>
                {result.origin} → {result.destination}
              </h2>
              <p className="font-body" style={{ fontSize: 12, color: '#5B6B84', marginTop: 2 }}>
                {result.options.length
                  ? `${result.options.length} route${result.options.length === 1 ? '' : 's'} found for ${result.passenger_name} — ranked by earliest arrival`
                  : `No routes found for ${result.passenger_name}`}
              </p>
            </div>
            <button
              type="button"
              onClick={resetSearch}
              className="font-body font-semibold"
              style={{
                fontSize: 12, color: '#1B6FC2', background: 'rgba(47,143,224,0.10)',
                border: '1px solid rgba(47,143,224,0.18)', borderRadius: 999,
                padding: '6px 14px', cursor: 'pointer',
              }}
            >
              ← New search
            </button>
          </div>

          {result.options.map((option, index) => {
            const isSelected = selected?.code === option.code
            return (
              <button
                key={`${option.code}-${index}`}
                type="button"
                onClick={() => setSelected(option)}
                className="text-left"
                style={{
                  background: isSelected ? '#F0FFF8' : '#fff',
                  border: isSelected ? '2px solid #2ECC87' : '1px solid rgba(47,143,224,0.13)',
                  borderRadius: 16, padding: 17, cursor: 'pointer',
                  boxShadow: isSelected ? '0 6px 20px rgba(46,204,135,0.14)' : '0 3px 12px rgba(27,42,65,0.04)',
                }}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono font-bold" style={{ fontSize: 15, color: '#1B2A41' }}>{option.code}</span>
                    {option.recommended && (
                      <span className="font-mono" style={{ fontSize: 9, color: '#1A9B65', background: '#DBF7EA', borderRadius: 999, padding: '3px 7px', textTransform: 'uppercase' }}>
                        Agent pick
                      </span>
                    )}
                    <span
                      className="font-mono"
                      style={{
                        fontSize: 9, borderRadius: 999, padding: '3px 7px', textTransform: 'uppercase',
                        color: option.source.includes('Atlas') ? '#1A9B65' : '#8A9BB5',
                        background: option.source.includes('Atlas') ? '#DBF7EA' : '#F1F5FB',
                      }}
                    >
                      {option.source}
                    </span>
                    {option.self_transfer && (
                      <span
                        className="font-mono"
                        style={{
                          fontSize: 9, borderRadius: 999, padding: '3px 7px', textTransform: 'uppercase',
                          color: '#B0730A', background: 'rgba(212,135,10,0.12)',
                        }}
                      >
                        {option.ticket_count} tickets · self-transfer
                      </span>
                    )}
                    {option.destination_mismatch && (
                      <span
                        className="font-mono"
                        style={{
                          fontSize: 9, borderRadius: 999, padding: '3px 7px', textTransform: 'uppercase',
                          color: '#C0392B', background: 'rgba(192,57,43,0.09)',
                        }}
                      >
                        Lands at {option.arrives_at}
                      </span>
                    )}
                  </div>
                  <div className="text-right">
                    <div className="font-mono font-bold" style={{ fontSize: 15, color: '#1B2A41' }}>
                      {formatDuration(option.duration_minutes)}
                    </div>
                    <div className="font-mono" style={{ fontSize: 10, color: '#8A9BB5' }}>
                      {describeStops(option)}
                    </div>
                  </div>
                </div>

                <div className="mt-3 flex flex-col gap-1">
                  {option.legs.map((leg, legIndex) => (
                    <div key={`${leg.flight_no}-${legIndex}`}>
                      <div className="font-body" style={{ fontSize: 12, color: '#5B6B84' }}>
                        <span className="font-mono font-bold" style={{ color: '#1B2A41' }}>{leg.flight_no}</span>
                        {' '}{leg.airline} · {leg.origin} {leg.departs} → {leg.destination} {leg.arrives}
                      </div>
                      {leg.layover_after_minutes !== null && (
                        <div
                          className="font-mono flex items-center gap-1 flex-wrap"
                          style={{
                            fontSize: 10, margin: '4px 0 4px 2px', padding: '4px 9px',
                            borderRadius: 8, width: 'fit-content',
                            color: leg.layover_tight ? '#C0392B' : '#B0730A',
                            background: leg.layover_tight ? 'rgba(192,57,43,0.08)' : 'rgba(212,135,10,0.09)',
                            border: `1px solid ${leg.layover_tight ? 'rgba(192,57,43,0.22)' : 'rgba(212,135,10,0.20)'}`,
                          }}
                        >
                          <span>⏱ {formatDuration(leg.layover_after_minutes)} transit gap in {leg.destination}</span>
                          {leg.layover_tight && (
                            <span style={{ fontWeight: 700, textTransform: 'uppercase' }}>· tight</span>
                          )}
                          {leg.self_transfer_after && (
                            <span style={{ fontWeight: 700, textTransform: 'uppercase' }}>
                              · ticket change, not protected
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                <div className="mt-3 flex flex-wrap gap-4 font-mono" style={{ fontSize: 11, color: '#5B6B84' }}>
                  <span>{option.airlines}</span>
                  {option.layover_minutes !== null && (
                    <span>{formatDuration(option.layover_minutes)} total on the ground</span>
                  )}
                  {option.price !== null && (
                    <span style={{ color: '#1A9B65', fontWeight: 700 }}>
                      {option.price.toFixed(2)} {option.currency}
                    </span>
                  )}
                </div>
              </button>
            )
          })}

          {result.options.length > 0 && (
            <ChatBubble variant="ai">
              <p className="font-body text-sm leading-relaxed" style={{ color: '#1B2A41' }}>
                🤖 <MdBold text={result.narrative} />
              </p>
            </ChatBubble>
          )}

          {result.options.length === 0 && (
            <div className="font-body" style={{ background: '#fff', borderRadius: 16, padding: 20, color: '#5B6B84', fontSize: 13, lineHeight: 1.6 }}>
              <p>{result.narrative}</p>
              <p style={{ marginTop: 8 }}>
                Try an earlier departure time. With the mock schedule, covered routes include
                DFW → ATL (direct), ORD → LAX (via DEN) and JFK → KIX (via NRT, Sep 4 2026);
                other pairs need live Atlas inventory.
              </p>
            </div>
          )}

          {selected && (
            <div
              className="animate-slide-up"
              style={{ background: '#fff', border: '1.5px solid #2ECC87', borderRadius: 18, padding: 20 }}
            >
              <div className="font-mono" style={{ fontSize: 10, color: '#1A9B65', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                Selection summary
              </div>
              <h3 className="font-display font-bold" style={{ fontSize: 17, color: '#1B2A41', marginTop: 6 }}>
                {selected.code} for {result.passenger_name}
              </h3>
              <p className="font-body" style={{ fontSize: 13, color: '#5B6B84', marginTop: 4 }}>
                {result.origin} {selected.departs} → {selected.arrives_at} {selected.arrives} ·{' '}
                {formatDuration(selected.duration_minutes)} · {describeStops(selected)}
                {selected.layover_minutes !== null && ` · ${formatDuration(selected.layover_minutes)} on the ground`}
                {selected.price !== null && ` · ${selected.price.toFixed(2)} ${selected.currency}`}
              </p>
              <p className="font-body" style={{ fontSize: 12, color: '#5B6B84', marginTop: 10, lineHeight: 1.6 }}>
                {selected.self_transfer && (
                  <span style={{ color: '#B0730A', fontWeight: 600 }}>
                    Heads-up: this is {selected.ticket_count} separate tickets with a self-transfer in{' '}
                    {selected.transfer_airport}. The passenger re-checks bags there, and if the first
                    flight runs late no airline is obliged to re-accommodate them — ticketing it means
                    {' '}{selected.ticket_count} separate Atlas orders.{' '}
                  </span>
                )}
                {selected.destination_mismatch && (
                  <span style={{ color: '#C0392B', fontWeight: 600 }}>
                    Note: this itinerary lands at {selected.arrives_at}, not the requested{' '}
                    {result.destination}. Confirm the passenger accepts that airport before booking.{' '}
                  </span>
                )}
                No booking has been made and nothing was charged. The next step is the booking
                workflow (Atlas verify → order → pay), which asks for explicit approval before
                any money moves. Click another option above to change the selection.
              </p>
            </div>
          )}
        </section>
      )}
    </div>
  )
}

/** Render the agent's **bold** markdown as React elements - no HTML injection. */
function MdBold({ text }: { text: string }) {
  const parts = text.split(/\*\*(.+?)\*\*/g)
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? <b key={i} style={{ color: '#1B6FC2' }}>{part}</b> : part,
      )}
    </>
  )
}
