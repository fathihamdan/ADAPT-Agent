import { ReactNode } from 'react'

interface Props {
  children: ReactNode
  className?: string
  style?: React.CSSProperties
}

export function Card({ children, className = '', style }: Props) {
  return (
    <div
      className={className}
      style={{
        background: '#ffffff',
        borderRadius: 24,
        boxShadow: '0 8px 32px rgba(47, 143, 224, 0.10), 0 2px 8px rgba(27,42,65,0.06)',
        padding: '20px',
        ...style,
      }}
    >
      {children}
    </div>
  )
}
