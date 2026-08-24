interface Props {
  percentage: number
}

function getEmojiAndColor(pct: number): { emoji: string; color: string; glow: string } {
  if (pct < 30) return { emoji: '😌', color: '#2ECC87', glow: 'rgba(46,204,135,0.25)' }
  if (pct < 60) return { emoji: '😬', color: '#FFB84C', glow: 'rgba(255,184,76,0.25)' }
  return { emoji: '😰', color: '#FF6B4A', glow: 'rgba(255,107,74,0.25)' }
}

export function RiskMeter({ percentage }: Props) {
  const { emoji, color, glow } = getEmojiAndColor(percentage)
  const size = 160
  const strokeWidth = 12
  const r = (size - strokeWidth) / 2
  const circ = 2 * Math.PI * r
  const arcLength = circ * 0.75
  const filled = arcLength * (percentage / 100)
  const offset = circ * 0.125

  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      {/* Pulse ring */}
      <div
        style={{
          position: 'absolute',
          inset: -8,
          borderRadius: '50%',
          border: `2px solid ${color}`,
          animation: 'pulse-ring 2s ease-in-out infinite',
          opacity: 0.4,
        }}
      />

      <svg width={size} height={size}>
        {/* Track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#E8F2FB"
          strokeWidth={strokeWidth}
          strokeDasharray={`${arcLength} ${circ - arcLength}`}
          strokeDashoffset={-offset}
          strokeLinecap="round"
          transform={`rotate(135 ${size / 2} ${size / 2})`}
        />
        {/* Fill */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={`${filled} ${circ - filled}`}
          strokeDashoffset={-offset}
          strokeLinecap="round"
          transform={`rotate(135 ${size / 2} ${size / 2})`}
          style={{
            filter: `drop-shadow(0 0 6px ${glow})`,
            transition: 'stroke-dasharray 0.05s linear',
          }}
        />
      </svg>

      {/* Center content */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 2,
        }}
      >
        <span style={{ fontSize: 28 }}>{emoji}</span>
        <div
          className="font-display font-bold"
          style={{ fontSize: 32, color, lineHeight: 1 }}
        >
          {percentage}%
        </div>
        <div
          className="font-mono"
          style={{ fontSize: 9, color: '#5B6B84', letterSpacing: '0.08em', textTransform: 'uppercase' }}
        >
          miss risk
        </div>
      </div>
    </div>
  )
}
