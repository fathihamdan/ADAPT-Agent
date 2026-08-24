interface Props {
  variant: 'coral' | 'sun' | 'leaf'
  label: string
  mono?: boolean
}

const styles = {
  coral: { bg: '#FFE3DB', color: '#FF6B4A' },
  sun: { bg: '#FFF1DA', color: '#D4870A' },
  leaf: { bg: '#DBF7EA', color: '#1A9B65' },
}

export function StatusPill({ variant, label, mono }: Props) {
  const s = styles[variant]
  return (
    <span
      className={mono ? 'font-mono' : 'font-body'}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        background: s.bg,
        color: s.color,
        borderRadius: 999,
        padding: '4px 12px',
        fontSize: 12,
        fontWeight: 700,
        letterSpacing: mono ? '0.06em' : '0.01em',
        textTransform: mono ? 'uppercase' : undefined,
      }}
    >
      {label}
    </span>
  )
}
