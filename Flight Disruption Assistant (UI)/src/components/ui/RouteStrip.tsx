import { Card } from './Card'

interface Props {
  from: string
  to: string
  fromCity: string
  toCity: string
}

export function RouteStrip({ from, to, fromCity, toCity }: Props) {
  return (
    <Card style={{ padding: '16px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ textAlign: 'left' }}>
          <div
            className="font-mono font-bold"
            style={{ fontSize: 24, color: '#1B2A41', letterSpacing: '0.06em' }}
          >
            {from}
          </div>
          <div className="font-body" style={{ fontSize: 11, color: '#5B6B84', marginTop: 2 }}>
            {fromCity}
          </div>
        </div>

        <div style={{ flex: 1, display: 'flex', alignItems: 'center', padding: '0 12px' }}>
          <div style={{ flex: 1, height: 1, background: '#E2EAF3' }} />
          <div style={{ margin: '0 8px', fontSize: 18 }}>✈️</div>
          <div style={{ flex: 1, height: 1, background: '#E2EAF3' }} />
        </div>

        <div style={{ textAlign: 'right' }}>
          <div
            className="font-mono font-bold"
            style={{ fontSize: 24, color: '#1B2A41', letterSpacing: '0.06em' }}
          >
            {to}
          </div>
          <div className="font-body" style={{ fontSize: 11, color: '#5B6B84', marginTop: 2 }}>
            {toCity}
          </div>
        </div>
      </div>
    </Card>
  )
}
