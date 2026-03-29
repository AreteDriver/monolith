import { useApi } from '../hooks/useApi'

const STATUS_COLORS = {
  up: '#22c55e',
  degraded: '#f59e0b',
  down: '#ef4444',
  unknown: '#6b7280',
  waiting: '#6b7280',
  ok: '#22c55e',
  slow: '#f59e0b',
  stalled: '#ef4444',
}

const STATUS_DOT = {
  up: 'bg-green-500',
  degraded: 'bg-amber-500',
  down: 'bg-red-500',
  unknown: 'bg-gray-500',
}

const SERVICE_LABELS = {
  world_api: 'Stillness (World API)',
  sui_rpc: 'Sui Chain (Testnet)',
  watchtower: 'WatchTower',
  event_lag: 'Event Processing',
  detection_health: 'Detection Engine',
}

function StatusDot({ status }) {
  const cls = STATUS_DOT[status] || STATUS_DOT.unknown
  const pulse = status === 'down' ? 'animate-pulse' : ''
  return <span className={`inline-block w-3 h-3 rounded-full ${cls} ${pulse}`} />
}

function TimeAgo({ ts }) {
  if (!ts) return <span className="text-[#6b7280]">—</span>
  const seconds = Math.floor(Date.now() / 1000) - ts
  if (seconds < 60) return <span>{seconds}s ago</span>
  if (seconds < 3600) return <span>{Math.floor(seconds / 60)}m ago</span>
  if (seconds < 86400) return <span>{Math.floor(seconds / 3600)}h ago</span>
  return <span>{Math.floor(seconds / 86400)}d ago</span>
}

function ServiceCard({ svc }) {
  const label = SERVICE_LABELS[svc.service_name] || svc.service_name.replace('loop:', '')
  return (
    <div className="border border-[#2a2a2a] bg-[#111111] p-4 rounded">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <StatusDot status={svc.status} />
          <span className="text-sm font-mono text-white">{label}</span>
        </div>
        <span
          className="text-xs font-bold px-2 py-0.5 rounded"
          style={{ color: STATUS_COLORS[svc.status] || '#6b7280' }}
        >
          {svc.status.toUpperCase()}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs text-[#a3a3a3]">
        <div>
          <span className="text-[#6b7280]">Response: </span>
          {svc.response_time_ms > 0 ? `${svc.response_time_ms}ms` : '—'}
        </div>
        <div>
          <span className="text-[#6b7280]">Checked: </span>
          <TimeAgo ts={svc.last_checked_at} />
        </div>
        <div>
          <span className="text-[#6b7280]">Last change: </span>
          <TimeAgo ts={svc.last_change_at} />
        </div>
        <div>
          <span className="text-[#6b7280]">Failures: </span>
          {svc.consecutive_failures}
        </div>
      </div>
      {svc.error_message && (
        <div className="mt-2 text-xs text-red-400 bg-red-950/30 border border-red-900/50 p-2 rounded font-mono break-all">
          {svc.error_message}
        </div>
      )}
    </div>
  )
}

function Sparkline({ checks }) {
  if (!checks || checks.length < 2) return null

  const data = [...checks].reverse()
  const maxMs = Math.max(...data.map(c => c.response_time_ms || 0), 1)
  const w = 200
  const h = 40
  const points = data.map((c, i) => {
    const x = (i / (data.length - 1)) * w
    const y = h - ((c.response_time_ms || 0) / maxMs) * h
    return `${x},${y}`
  }).join(' ')

  const colors = data.map(c =>
    c.status === 'down' ? '#ef4444' : c.status === 'degraded' ? '#f59e0b' : '#22c55e'
  )
  const lastColor = colors[colors.length - 1]

  return (
    <svg width={w} height={h} className="mt-2">
      <polyline
        points={points}
        fill="none"
        stroke={lastColor}
        strokeWidth="1.5"
        opacity="0.8"
      />
      {data.map((c, i) => {
        const x = (i / (data.length - 1)) * w
        const y = h - ((c.response_time_ms || 0) / maxMs) * h
        return (
          <circle
            key={i}
            cx={x}
            cy={y}
            r="2"
            fill={colors[i]}
          />
        )
      })}
    </svg>
  )
}

function HistoryPanel({ serviceName }) {
  const { data } = useApi(`/api/status/history?service=${serviceName}&limit=30`, { poll: 60000 })

  if (!data?.checks?.length) return null

  const avgMs = Math.round(
    data.checks.reduce((sum, c) => sum + (c.response_time_ms || 0), 0) / data.checks.length
  )

  return (
    <div className="border border-[#2a2a2a] bg-[#111111] p-3 rounded">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-mono text-[#a3a3a3]">{SERVICE_LABELS[serviceName] || serviceName}</span>
        <span className="text-xs text-[#6b7280]">avg {avgMs}ms</span>
      </div>
      <Sparkline checks={data.checks} />
    </div>
  )
}

export default function StatusPage() {
  const { data, loading, error } = useApi('/api/status', { poll: 30000 })

  if (loading) return <p className="text-[#a3a3a3]">Loading status...</p>
  if (error) return <p className="text-red-400">Failed to load status: {error}</p>
  if (!data) return <p className="text-[#a3a3a3]">No status data.</p>

  const externalServices = (data.services || []).filter(
    s => !s.service_name.startsWith('loop:') &&
      !['event_lag', 'detection_health'].includes(s.service_name)
  )
  const internalServices = (data.services || []).filter(
    s => s.service_name.startsWith('loop:') ||
      ['event_lag', 'detection_health'].includes(s.service_name)
  )

  const overallColor = STATUS_COLORS[data.overall] || STATUS_COLORS.unknown

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-white">Service Status</h1>
        <div className="flex items-center gap-3">
          <StatusDot status={data.overall} />
          <span className="text-sm font-bold" style={{ color: overallColor }}>
            {data.overall.toUpperCase()}
          </span>
          <span className="text-xs text-[#6b7280]">
            Updated <TimeAgo ts={data.checked_at} />
          </span>
        </div>
      </div>

      {/* External Services */}
      <h2 className="text-sm font-bold text-[#a3a3a3] uppercase tracking-wider mb-3">
        EVE Frontier Services
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {externalServices.map(svc => (
          <ServiceCard key={svc.service_name} svc={svc} />
        ))}
      </div>

      {/* Response Time History */}
      {externalServices.length > 0 && (
        <>
          <h2 className="text-sm font-bold text-[#a3a3a3] uppercase tracking-wider mb-3">
            Response Time (last 30 checks)
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            {externalServices.map(svc => (
              <HistoryPanel key={svc.service_name} serviceName={svc.service_name} />
            ))}
          </div>
        </>
      )}

      {/* Monolith Self-Health */}
      <h2 className="text-sm font-bold text-[#a3a3a3] uppercase tracking-wider mb-3">
        Monolith Health
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {/* Loop Status */}
        <div className="border border-[#2a2a2a] bg-[#111111] p-4 rounded">
          <h3 className="text-xs font-bold text-[#6b7280] uppercase mb-3">Background Loops</h3>
          <div className="space-y-2">
            {Object.entries(data.monolith?.loops || {}).map(([name, status]) => (
              <div key={name} className="flex items-center justify-between text-xs">
                <span className="font-mono text-[#a3a3a3]">{name}</span>
                <span
                  className="font-bold"
                  style={{ color: STATUS_COLORS[status] || '#6b7280' }}
                >
                  {status.toUpperCase()}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Metrics */}
        <div className="border border-[#2a2a2a] bg-[#111111] p-4 rounded">
          <h3 className="text-xs font-bold text-[#6b7280] uppercase mb-3">Processing Metrics</h3>
          <div className="space-y-3">
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-[#a3a3a3]">Event Lag</span>
                <span className="font-mono text-white">
                  {data.monolith?.event_lag?.toLocaleString() ?? '—'}
                </span>
              </div>
              <div className="w-full bg-[#1a1a1a] rounded h-1.5">
                <div
                  className="h-1.5 rounded"
                  style={{
                    width: `${Math.min((data.monolith?.event_lag || 0) / 50, 100)}%`,
                    backgroundColor:
                      data.monolith?.event_lag > 5000
                        ? '#ef4444'
                        : data.monolith?.event_lag > 1000
                        ? '#f59e0b'
                        : '#22c55e',
                  }}
                />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-[#a3a3a3]">Detection Error Rate</span>
                <span className="font-mono text-white">
                  {data.monolith?.detection_error_rate !== undefined
                    ? `${Math.round(data.monolith.detection_error_rate * 100)}%`
                    : '—'}
                </span>
              </div>
              <div className="w-full bg-[#1a1a1a] rounded h-1.5">
                <div
                  className="h-1.5 rounded"
                  style={{
                    width: `${Math.min((data.monolith?.detection_error_rate || 0) * 100, 100)}%`,
                    backgroundColor:
                      data.monolith?.detection_error_rate > 0.8
                        ? '#ef4444'
                        : data.monolith?.detection_error_rate > 0.5
                        ? '#f59e0b'
                        : '#22c55e',
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Internal Service Cards */}
      {internalServices.length > 0 && (
        <>
          <h2 className="text-sm font-bold text-[#a3a3a3] uppercase tracking-wider mb-3">
            Internal Monitors
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {internalServices.map(svc => (
              <ServiceCard key={svc.service_name} svc={svc} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
