import { useEffect, useState } from 'react'
import { StatusPill } from './ui/StatusPill'
import { RouteStrip } from './ui/RouteStrip'
import { ChatBubble } from './ui/ChatBubble'
import { PrimaryButton } from './ui/PrimaryButton'
import type { Disruption } from '../types'
import { causeCopy } from '../causeCopy'

interface Props {
  disruption: Disruption | null
  onNext: () => void
}

export default function FrameDisruption({ disruption, onNext }: Props) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 60)
    return () => clearTimeout(t)
  }, [])

  const kicker = disruption ? causeCopy(disruption.cause) : { emoji: '✅', label: 'On schedule' }

  return (
    <div
      className="flex flex-col justify-between px-6 pt-8 pb-8"
      style={{
        minHeight: 560,
        opacity: visible ? 1 : 0,
        transition: 'opacity 0.4s ease',
      }}
    >
      {/* Kicker */}
      <div>
        <p
          className="font-mono text-xs font-bold uppercase tracking-widest mb-2 animate-slide-up"
          style={{ color: disruption ? '#FF6B4A' : '#2ECC87', animationDelay: '0.1s', opacity: 0, animationFillMode: 'forwards' }}
        >
          {kicker.emoji} {kicker.label}
        </p>

        <h1
          className="font-display font-bold leading-tight mb-4 animate-slide-up"
          style={{
            fontSize: 28,
            color: '#1B2A41',
            animationDelay: '0.2s',
            opacity: 0,
            animationFillMode: 'forwards',
          }}
        >
          {disruption ? (
            <>
              Your flight&apos;s {disruption.status === 'CANCELLED' ? 'cancelled' : 'delayed'}.{' '}
              <span style={{ color: '#5B6B84' }}>Here&apos;s why,</span>
              <br />in plain English.
            </>
          ) : (
            <>
              You&apos;re all set.{' '}
              <span style={{ color: '#5B6B84' }}>No disruption</span>
              <br />on this itinerary.
            </>
          )}
        </h1>

        {disruption && (
          <>
            {/* Pills row */}
            <div
              className="flex gap-2 mb-5 animate-slide-up"
              style={{ animationDelay: '0.3s', opacity: 0, animationFillMode: 'forwards' }}
            >
              <StatusPill variant="coral" label={disruption.flight_no} mono />
              {disruption.status === 'CANCELLED' ? (
                <StatusPill variant="sun" label="Cancelled" />
              ) : (
                <StatusPill variant="sun" label={`+${disruption.delay_minutes}m delay`} />
              )}
            </div>

            {/* Route strip */}
            <div
              className="mb-5 animate-slide-up"
              style={{ animationDelay: '0.35s', opacity: 0, animationFillMode: 'forwards' }}
            >
              <RouteStrip
                from={disruption.origin}
                to={disruption.destination}
                fromCity={disruption.origin_city}
                toCity={disruption.destination_city}
              />
            </div>

            {/* Bubble pair */}
            <div
              className="flex flex-col gap-3 animate-slide-up"
              style={{ animationDelay: '0.45s', opacity: 0, animationFillMode: 'forwards' }}
            >
              <ChatBubble variant="raw">
                <span className="font-mono text-xs" style={{ color: '#5B6B84', letterSpacing: '0.04em' }}>
                  {disruption.raw_feed}
                </span>
              </ChatBubble>

              <ChatBubble variant="ai">
                <p
                  className="font-body text-sm font-medium leading-relaxed"
                  style={{ color: '#1B2A41' }}
                  dangerouslySetInnerHTML={{ __html: `✈️ ${disruption.ai_html}` }}
                />
              </ChatBubble>
            </div>
          </>
        )}
      </div>

      {/* CTA */}
      <div
        className="mt-6 animate-slide-up"
        style={{ animationDelay: '0.6s', opacity: 0, animationFillMode: 'forwards' }}
      >
        <PrimaryButton onClick={onNext} icon="→">
          {disruption ? 'Will I miss my connection?' : 'Check connection anyway'}
        </PrimaryButton>
      </div>
    </div>
  )
}
