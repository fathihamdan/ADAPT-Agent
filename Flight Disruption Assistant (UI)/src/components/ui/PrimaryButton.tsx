import { ReactNode } from 'react'

interface Props {
  children: ReactNode
  onClick?: () => void
  icon?: string
  variant?: 'sky' | 'coral' | 'leaf'
}

const gradients = {
  sky: 'linear-gradient(135deg, #2F8FE0 0%, #5BAAEF 100%)',
  coral: 'linear-gradient(135deg, #FF6B4A 0%, #FF9070 100%)',
  leaf: 'linear-gradient(135deg, #2ECC87 0%, #56E5A6 100%)',
}

export function PrimaryButton({ children, onClick, icon, variant = 'sky' }: Props) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        width: '100%',
        background: gradients[variant],
        color: '#ffffff',
        border: 'none',
        borderRadius: 999,
        padding: '16px 24px',
        fontSize: 16,
        fontFamily: 'Inter, sans-serif',
        fontWeight: 700,
        cursor: 'pointer',
        boxShadow: '0 4px 20px rgba(47,143,224,0.25)',
        transition: 'transform 0.15s ease, box-shadow 0.15s ease',
        letterSpacing: '0.01em',
      }}
      onMouseDown={e => (e.currentTarget.style.transform = 'scale(0.97)')}
      onMouseUp={e => (e.currentTarget.style.transform = 'scale(1)')}
      onMouseLeave={e => (e.currentTarget.style.transform = 'scale(1)')}
    >
      <span>{children}</span>
      {icon && <span style={{ fontSize: 18 }}>{icon}</span>}
    </button>
  )
}
