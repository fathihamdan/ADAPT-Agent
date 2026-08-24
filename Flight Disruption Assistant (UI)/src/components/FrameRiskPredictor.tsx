import { useEffect, useState } from 'react'
import { StatusPill } from './ui/StatusPill'
import { ChatBubble } from './ui/ChatBubble'
import { PrimaryButton } from './ui/PrimaryButton'
import { RiskMeter } from './ui/RiskMeter'
import { StepTracker } from './ui/StepTracker'
import type { Connection } from '../types'

interface Props {
  connection: Connection | null
  active: boolean
  onNext: () => void
}

export default function FrameRiskPredictor({ connection, active, onNext }: Props) {
  const [count, setCount] = useState(0)
  const [visible, setVisible] = useState(false)
  const targetRisk = connection?.risk_pct ?? 0

  useEffect(() => {
    if (!active) {
      setCount(0)
      setVisible(false)
      return
    }
    const t = setTimeout(() => setVisible(true), 60)
    return () => clearTimeout(t)
  }, [active])

  useEffect(() => {
    if (!visible) return
    let start: number
    const duration = 1800

    const animate = (ts: number) => {
      if (!start) start = ts
      const elapsed = ts - start
      const pct = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - pct, 3)
      setCount(Math.round(eased * targetRisk))
      if (pct < 1) requestAnimationFrame(animate)
    }

    const raf = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(raf)
  }, [visible, targetRisk])

  const severe = !!connection && (connection.risk_level === 'HIGH' || connection.risk_level === 'CRITICAL')
  const cutoff = connection?.steps.find(s => s[0] === 'Cutoff')

  return (
    <div
      className="flex flex-col justify-between px-6 pt-8 pb-8"
      style={{
        minHeight: 560,
        opacity: visible ? 1 : 0,
        transition: 'opacity 0.4s ease',
      }}
    >
      <div>
        <p
          className="font-mono text-xs font-bold uppercase tracking-widest mb-2"
          style={{ color: connection ? (severe ? '#FF6B4A' : '#FFB84C') : '#2ECC87' }}
        >
          {connection ? '🏃 Tight connection ahead' : '✅ No connection to assess'}
        </p>

        {connection ? (
          <>
            <h1
              className="font-display font-bold leading-tight mb-1"
              style={{ fontSize: 27, color: '#1B2A41' }}
            >
              Your connection to {connection.to} is at{' '}
              <span style={{ color: severe ? '#FF6B4A' : '#D4870A' }}>
                {severe ? 'serious risk.' : 'some risk.'}
              </span>
            </h1>

            <p className="font-body text-sm mb-5" style={{ color: '#5B6B84' }}>
              {connection.buffer_min >= 0
                ? `You'll have about ${connection.buffer_min} minutes of buffer at ${connection.from}.`
                : `You'd need about ${Math.abs(connection.buffer_min)} more minutes than you'll have at ${connection.from}.`}
            </p>

            {/* Pills */}
            <div className="flex gap-2 mb-6">
              <StatusPill variant="coral" label={`${connection.from} → ${connection.to}`} mono />
              {cutoff && <StatusPill variant="sun" label={`Gate closes ${cutoff[1]}`} mono />}
            </div>

            {/* Risk meter */}
            <div className="flex justify-center mb-6">
              <RiskMeter percentage={count} />
            </div>

            {/* Step tracker */}
            <div className="mb-5">
              <StepTracker
                steps={connection.steps.map(([label, time, status]) => ({
                  label,
                  time,
                  done: false,
                  risk: status === 'warn',
                }))}
              />
            </div>

            {/* AI bubble */}
            <ChatBubble variant="ai">
              <p className="font-body text-sm leading-relaxed" style={{ color: '#1B2A41' }}>
                🤖 {connection.ai_text}
              </p>
            </ChatBubble>
          </>
        ) : (
          <>
            <h1
              className="font-display font-bold leading-tight mb-1"
              style={{ fontSize: 27, color: '#1B2A41' }}
            >
              Nothing to <span style={{ color: '#2ECC87' }}>connect to.</span>
            </h1>
            <p className="font-body text-sm mb-5" style={{ color: '#5B6B84' }}>
              This itinerary has a single leg, or the connecting flight was already cancelled.
            </p>
          </>
        )}
      </div>

      <div className="mt-6">
        <PrimaryButton onClick={onNext} icon="→" variant={severe ? 'coral' : 'leaf'}>
          {connection ? 'Show me a safer option' : 'Continue'}
        </PrimaryButton>
      </div>
    </div>
  )
}
