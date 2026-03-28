/**
 * EmbeddedView — Compact threat feed for in-game Smart Assembly browser panels.
 *
 * Designed for ~400px wide assembly browser windows.
 * Shows live anomalies, severity badges, and links to full Monolith dashboard.
 * No navigation chrome. Auto-polls every 30s.
 *
 * Routes:
 *   /embed              — general threat feed
 *   /embed?system=0x... — filtered to a specific system
 */
import { useSearchParams } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { getDisplayName } from '../displayNames'

const SEVERITY_COLORS = {
  CRITICAL: { bg: '#ff333315', text: '#ff3333', border: '#ff333330' },
  HIGH:     { bg: '#ff660015', text: '#ff6600', border: '#ff660030' },
  MEDIUM:   { bg: '#ffcc0015', text: '#ffcc00', border: '#ffcc0030' },
  LOW:      { bg: '#22c55e15', text: '#22c55e', border: '#22c55e30' },
}

function timeAgo(ts) {
  const seconds = Math.floor((Date.now() / 1000) - ts)
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

export default function EmbeddedView() {
  const [searchParams] = useSearchParams()
  const systemId = searchParams.get('system')

  const critUrl = systemId
    ? `/api/anomalies?limit=5&severity=CRITICAL&system_id=${systemId}`
    : '/api/anomalies?limit=5&severity=CRITICAL'
  const highUrl = systemId
    ? `/api/anomalies?limit=5&severity=HIGH&system_id=${systemId}`
    : '/api/anomalies?limit=5&severity=HIGH'

  const { data: critData } = useApi(critUrl, { poll: 30000 })
  const { data: highData } = useApi(highUrl, { poll: 30000 })
  const { data: statsData } = useApi('/api/health', { poll: 60000 })

  const criticals = critData?.data || []
  const highs = highData?.data || []
  const threats = [...criticals, ...highs]
    .sort((a, b) => b.detected_at - a.detected_at)
    .slice(0, 8)

  const anomalyCount = statsData?.tables?.anomalies || 0
  const eventCount = statsData?.tables?.chain_events || 0

  return (
    <div style={{
      padding: 12,
      maxWidth: 420,
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      backgroundColor: '#0a0a0a',
      color: '#e5e5e5',
      minHeight: '100vh',
    }}>
      {/* Header */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ color: '#f59e0b', fontSize: 11, fontWeight: 700, letterSpacing: '0.15em' }}>
              MONOLITH
            </div>
            <div style={{ color: '#6b7280', fontSize: 9 }}>
              Blockchain Integrity Monitor
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ color: '#6b7280', fontSize: 9 }}>
              {anomalyCount} anomalies / {eventCount} events
            </div>
          </div>
        </div>
        {systemId && (
          <div style={{ marginTop: 4, fontSize: 9, color: '#6b7280' }}>
            Filtered: <span style={{ color: '#e5e5e5' }}>{systemId.slice(0, 10)}...{systemId.slice(-4)}</span>
          </div>
        )}
      </div>

      {/* Threat Status */}
      {threats.length === 0 ? (
        <div style={{
          border: '1px solid #2a2a2a',
          padding: 12,
          marginBottom: 8,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%',
              backgroundColor: '#22c55e',
              display: 'inline-block',
            }} />
            <span style={{ color: '#22c55e', fontSize: 11, fontWeight: 700, letterSpacing: '0.1em' }}>
              ALL CLEAR
            </span>
          </div>
          <div style={{ color: '#6b7280', fontSize: 10, marginTop: 4 }}>
            No CRITICAL or HIGH threats detected.
          </div>
        </div>
      ) : (
        <div style={{
          border: '1px solid #ff333320',
          backgroundColor: '#ff333308',
          padding: 8,
          marginBottom: 8,
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            marginBottom: 8,
          }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%',
              backgroundColor: '#ff3333',
              display: 'inline-block',
              animation: 'pulse 1.5s ease-in-out infinite',
            }} />
            <span style={{ color: '#ff3333', fontSize: 11, fontWeight: 700, letterSpacing: '0.1em' }}>
              LIVE THREATS
            </span>
            <span style={{ color: '#6b7280', fontSize: 9, marginLeft: 'auto' }}>
              {threats.length} active
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {threats.map((a) => {
              const colors = SEVERITY_COLORS[a.severity] || SEVERITY_COLORS.LOW
              return (
                <div
                  key={a.anomaly_id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '4px 6px',
                    backgroundColor: '#111111',
                    borderLeft: `2px solid ${colors.text}`,
                  }}
                >
                  <span style={{
                    fontSize: 8,
                    fontWeight: 700,
                    color: colors.text,
                    backgroundColor: colors.bg,
                    border: `1px solid ${colors.border}`,
                    padding: '1px 4px',
                    borderRadius: 2,
                    textTransform: 'uppercase',
                    flexShrink: 0,
                  }}>
                    {a.severity}
                  </span>
                  <span style={{
                    fontSize: 10,
                    color: '#e5e5e5',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    flex: 1,
                  }}>
                    {getDisplayName(a)}
                  </span>
                  <span style={{ fontSize: 9, color: '#6b7280', flexShrink: 0 }}>
                    {timeAgo(a.detected_at)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Detection Rules Summary */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 6,
        marginBottom: 8,
      }}>
        <div style={{
          backgroundColor: '#111111',
          border: '1px solid #2a2a2a',
          padding: 8,
          textAlign: 'center',
        }}>
          <div style={{ fontSize: 9, color: '#6b7280', textTransform: 'uppercase' }}>Rules Active</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#f59e0b' }}>35</div>
        </div>
        <div style={{
          backgroundColor: '#111111',
          border: '1px solid #2a2a2a',
          padding: 8,
          textAlign: 'center',
        }}>
          <div style={{ fontSize: 9, color: '#6b7280', textTransform: 'uppercase' }}>Checkers</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#f59e0b' }}>17</div>
        </div>
      </div>

      {/* Footer */}
      <div style={{ textAlign: 'center', marginTop: 8 }}>
        <a
          href="https://monolith-evefrontier.vercel.app/anomalies"
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: '#6b7280', fontSize: 9, textDecoration: 'none' }}
        >
          Full dashboard on Monolith →
        </a>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  )
}
