import { useEffect, useState } from 'react'
import { ChatBubble } from './ui/ChatBubble'
import { PrimaryButton } from './ui/PrimaryButton'
import { OptionCard } from './ui/OptionCard'
import type { Reroute, RerouteOption } from '../types'

interface Props {
  reroute: Reroute | null
  active: boolean
  onNext: () => void
  /** Book the chosen option: moves the passenger out of the queue. */
  onConfirm?: (option: RerouteOption) => void
  confirming?: boolean
}

export default function FrameRerouting({ reroute, active, onNext, onConfirm, confirming = false }: Props) {
  const [visible, setVisible] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(0)

  // Default to whichever option the backend recommended, but let the desk
  // override it - the ranking is advice, and the person confirming is the one
  // who knows about the passenger's bag, visa or onward plans.
  useEffect(() => {
    if (!reroute) return
    const recommended = reroute.options.findIndex(o => o.recommended)
    setSelectedIndex(recommended >= 0 ? recommended : 0)
  }, [reroute])

  // Three distinct outcomes, not two. The middle one - a search that ran and came
  // back empty - used to fall into the success branch and render "You're covered /
  // Found you a better connection" above "0 alternatives found", which tells an
  // ops desk the opposite of the truth about a passenger who still needs help.
  const hasOptions = !!reroute && reroute.options.length > 0
  const searchedAndEmpty = !!reroute && reroute.options.length === 0

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
          style={{ color: searchedAndEmpty ? '#C2410C' : '#2ECC87' }}
        >
          {searchedAndEmpty ? '⚠ No cover found' : '✅ You’re covered'}
        </p>

        {hasOptions && reroute ? (
          <>
            <h1
              className="font-display font-bold leading-tight mb-1"
              style={{ fontSize: 27, color: '#1B2A41' }}
            >
              Found you a{' '}
              <span style={{ color: '#2ECC87' }}>better connection.</span>
            </h1>

            <p className="font-body text-sm mb-5" style={{ color: '#5B6B84' }}>
              {reroute.options.length} alternative{reroute.options.length !== 1 ? 's' : ''} found, best first.
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
                  selected={onConfirm ? i === selectedIndex : false}
                  onSelect={onConfirm ? () => setSelectedIndex(i) : undefined}
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
        ) : searchedAndEmpty && reroute ? (
          <>
            <h1
              className="font-display font-bold leading-tight mb-1"
              style={{ fontSize: 27, color: '#1B2A41' }}
            >
              No alternatives{' '}
              <span style={{ color: '#C2410C' }}>available.</span>
            </h1>

            <p className="font-body text-sm mb-5" style={{ color: '#5B6B84' }}>
              This passenger still needs help — the search found nothing to rebook them onto.
            </p>

            {/* The narrative is the only thing that says *why* the search came back
                empty (no inventory, no through-fare, an upstream API error), so it
                is the most important element on the screen in this state. */}
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
        <PrimaryButton
          onClick={() => {
            const chosen = hasOptions && reroute ? reroute.options[selectedIndex] : undefined
            if (onConfirm && chosen) onConfirm(chosen)
            else onNext()
          }}
          variant={searchedAndEmpty ? 'coral' : 'leaf'}
          icon={searchedAndEmpty ? '↩' : '✓'}
        >
          {!hasOptions
            ? 'Back to start'
            : confirming
              ? 'Rebooking…'
              : onConfirm
                ? `Rebook onto ${reroute?.options[selectedIndex]?.code ?? 'this option'}`
                : 'Confirm my new flight'}
        </PrimaryButton>
      </div>
    </div>
  )
}
