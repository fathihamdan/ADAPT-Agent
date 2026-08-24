// Presentation-only copy derived from the real `cause` enum the backend returns.
// Not fabricated data - just an emoji/label pairing for a category we already have.
const CAUSE_COPY: Record<string, { emoji: string; label: string }> = {
  WEATHER: { emoji: '⛈️', label: 'Storms rolling in' },
  ATC: { emoji: '🗼', label: 'Air traffic control delay' },
  MECHANICAL: { emoji: '🔧', label: 'Mechanical check' },
  CREW: { emoji: '👥', label: 'Crew scheduling' },
  SECURITY: { emoji: '🛂', label: 'Security matter' },
  LATE_INBOUND_AIRCRAFT: { emoji: '✈️', label: 'Inbound aircraft running late' },
  NONE: { emoji: 'ℹ️', label: 'Status update' },
}

export function causeCopy(cause: string): { emoji: string; label: string } {
  return CAUSE_COPY[cause] ?? CAUSE_COPY.NONE
}
