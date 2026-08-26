interface Props {
  flight: string
  route: string
  departs: string
  arrives: string
  connections: number
  delayVsOriginal: number
  best: boolean
  animationDelay?: number
  /** Marks the card the confirm button will act on. */
  selected?: boolean
  onSelect?: () => void
}

export function OptionCard({
  flight, route, departs, arrives, connections, delayVsOriginal, best,
  animationDelay = 0, selected = false, onSelect,
}: Props) {
  const badgeColor = delayVsOriginal <= 0 ? '#1A9B65' : delayVsOriginal <= 180 ? '#D4870A' : '#FF6B4A'
  const badgeBg = delayVsOriginal <= 0 ? '#DBF7EA' : delayVsOriginal <= 180 ? '#FFF1DA' : '#FFE3DB'
  const badgeLabel = `${delayVsOriginal >= 0 ? '+' : ''}${delayVsOriginal}m`
  const stopsLabel = connections === 0 ? 'Direct' : `${connections} stop${connections > 1 ? 's' : ''}`

  return (
    <div
      onClick={onSelect}
      role={onSelect ? 'button' : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={onSelect ? e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect() } } : undefined}
      style={{
        background: best ? 'linear-gradient(135deg, #F0FFF8 0%, #E8FAF3 100%)' : '#ffffff',
        // Selection outranks "best pick" visually: the desk needs to see which
        // option the confirm button will actually book, not which one we ranked.
        border: selected
          ? '2px solid #2F8FE0'
          : best ? '2px solid #2ECC87' : '1.5px solid #E8EEF6',
        borderRadius: 20,
        padding: '14px 16px',
        boxShadow: selected
          ? '0 6px 24px rgba(47,143,224,0.22)'
          : best ? '0 6px 24px rgba(46,204,135,0.15)' : '0 2px 10px rgba(27,42,65,0.05)',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        cursor: onSelect ? 'pointer' : undefined,
        animation: `slideUp 0.5s ease ${animationDelay}s forwards`,
        opacity: 0,
        animationFillMode: 'forwards',
      }}
    >
      {/* Left: flight info */}
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <span
            className="font-mono font-bold"
            style={{ fontSize: 15, color: '#1B2A41', letterSpacing: '0.06em' }}
          >
            {flight}
          </span>
          {best && (
            <span
              style={{
                background: '#2ECC87',
                color: '#ffffff',
                fontSize: 9,
                fontWeight: 700,
                padding: '2px 7px',
                borderRadius: 999,
                fontFamily: 'Inter, sans-serif',
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
              }}
            >
              Best pick
            </span>
          )}
        </div>

        <div
          className="font-mono"
          style={{ fontSize: 11, color: '#5B6B84', letterSpacing: '0.04em', marginBottom: 3 }}
        >
          {route} · {departs} → {arrives}
        </div>

        <div
          className="font-body"
          style={{ fontSize: 11, color: '#8A9BB5' }}
        >
          {stopsLabel}
        </div>
      </div>

      {/* Right: delay-vs-original badge */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          background: badgeBg,
          borderRadius: 12,
          padding: '8px 10px',
          minWidth: 52,
        }}
      >
        <span
          className="font-display font-bold"
          style={{ fontSize: 18, color: badgeColor, lineHeight: 1 }}
        >
          {badgeLabel}
        </span>
        <span
          className="font-mono"
          style={{ fontSize: 8, color: badgeColor, letterSpacing: '0.06em', textTransform: 'uppercase', marginTop: 2 }}
        >
          vs plan
        </span>
      </div>
    </div>
  )
}
