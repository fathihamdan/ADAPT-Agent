import { ReactNode } from 'react'

interface Props {
  variant: 'raw' | 'ai'
  children: ReactNode
}

export function ChatBubble({ variant, children }: Props) {
  if (variant === 'raw') {
    return (
      <div
        style={{
          background: '#F4F7FB',
          border: '1.5px dashed #C8D6E8',
          borderRadius: 16,
          padding: '12px 16px',
        }}
      >
        {children}
      </div>
    )
  }

  return (
    <div
      style={{
        background: '#ffffff',
        border: '1.5px solid #2F8FE0',
        borderRadius: 18,
        borderTopLeftRadius: 4,
        padding: '14px 16px',
        boxShadow: '0 4px 16px rgba(47,143,224,0.10)',
        position: 'relative',
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: -1,
          left: 0,
          right: 0,
          height: 3,
          borderRadius: '18px 18px 0 0',
          background: 'linear-gradient(90deg, #2F8FE0 0%, #8FD3FF 100%)',
        }}
      />
      {children}
    </div>
  )
}
