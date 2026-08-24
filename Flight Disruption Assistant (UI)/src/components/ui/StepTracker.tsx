interface Step {
  label: string
  time: string
  done: boolean
  risk?: boolean
}

interface Props {
  steps: Step[]
}

export function StepTracker({ steps }: Props) {
  return (
    <div
      style={{
        background: '#ffffff',
        borderRadius: 20,
        padding: '16px 12px',
        boxShadow: '0 4px 16px rgba(27,42,65,0.06)',
        display: 'flex',
        alignItems: 'flex-start',
        gap: 0,
      }}
    >
      {steps.map((step, i) => {
        const isLast = i === steps.length - 1
        const dotColor = step.done
          ? '#2ECC87'
          : step.risk
            ? '#FF6B4A'
            : '#CBD5E1'

        return (
          <div key={i} style={{ display: 'flex', alignItems: 'center', flex: isLast ? 0 : 1 }}>
            {/* Node */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
              <div
                style={{
                  width: 30,
                  height: 30,
                  borderRadius: '50%',
                  background: step.risk ? '#FFE3DB' : '#F1F5FB',
                  border: `2px solid ${dotColor}`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 12,
                }}
              >
                {step.done ? (
                  <span style={{ color: '#2ECC87' }}>✓</span>
                ) : step.risk ? (
                  <span>⚡</span>
                ) : (
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: dotColor, display: 'block' }} />
                )}
              </div>
              <div
                className="font-mono font-bold"
                style={{ fontSize: 10, color: step.risk ? '#FF6B4A' : '#5B6B84', letterSpacing: '0.04em', textAlign: 'center' }}
              >
                {step.label}
              </div>
              <div
                className="font-mono"
                style={{ fontSize: 9, color: '#8A9BB5', letterSpacing: '0.04em' }}
              >
                {step.time}
              </div>
            </div>

            {/* Connector */}
            {!isLast && (
              <div
                style={{
                  flex: 1,
                  height: 2,
                  marginBottom: 30,
                  background: steps[i + 1]?.risk
                    ? 'linear-gradient(90deg, #FF6B4A, #FFB84C)'
                    : '#E2EAF3',
                  borderRadius: 1,
                }}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
