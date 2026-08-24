import { useEffect, useState } from 'react'
import { ChatBubble } from './ui/ChatBubble'
import { PrimaryButton } from './ui/PrimaryButton'
import { OptionCard } from './ui/OptionCard'
import type { Reroute } from '../types'

interface Props {
  reroute: Reroute | null
  active: boolean
  onNext: () => void
}

export default function FrameRerouting({ reroute, active, onNext }: Props) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!active) { setVisible(false); return }
    const t = setTimeout(() => setVisible(true), 60)
    return () => clearTimeout(t)
  }, [active])

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
          style={{ color: '#2ECC87' }}
        >
          ✅ You&apos;re covered
        </p>

        {reroute ? (
          <>
            <h1
              className="font-display font-bold leading-tight mb-1"
              style={{ fontSize: 27, color: '#1B2A41' }}
            >
              Found you a{' '}
              <span style={{ color: '#2ECC87' }}>better connection.</span>
            </h1>

            <p className="font-body text-sm mb-5" style={{ color: '#5B6B84' }}>
              {reroute.options.length} alternative{reroute.options.length !== 1 ? 's' : ''} found. Here&apos;s what I found.
            </p>

            {/* Option cards */}
            <div className="flex flex-col gap-3 mb-5">
              {reroute.options.map((opt, i) => (
                <OptionCard
                  key={opt.code + i}
                  flight={opt.code}
                  route={opt.route}
                  departs={opt.depart}
                  arrives={opt.arrival}
                  connections={opt.connections}
                  delayVsOriginal={opt.delay_vs_original}
                  best={opt.recommended}
                  animationDelay={i * 0.1}
                />
              ))}
            </div>

            {/* AI reasoning */}
            <ChatBubble variant="ai">
              <p className="font-body text-sm leading-relaxed" style={{ color: '#1B2A41' }}>
                🤖 {reroute.narrative}
              </p>
            </ChatBubble>
          </>
        ) : (
          <>
            <h1
              className="font-display font-bold leading-tight mb-1"
              style={{ fontSize: 27, color: '#1B2A41' }}
            >
              No rerouting <span style={{ color: '#2ECC87' }}>needed.</span>
            </h1>
            <p className="font-body text-sm mb-5" style={{ color: '#5B6B84' }}>
              This itinerary is on track — nothing to rebook right now.
            </p>
          </>
        )}
      </div>

      <div className="mt-6">
        <PrimaryButton onClick={onNext} variant="leaf" icon="✓">
          {reroute ? 'Confirm my new flight' : 'Back to start'}
        </PrimaryButton>
      </div>
    </div>
  )
}
