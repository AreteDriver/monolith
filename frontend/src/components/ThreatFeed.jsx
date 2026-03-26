/**
 * Live Threat Feed — auto-updating widget showing recent CRITICAL/HIGH anomalies.
 * Polls every 30s. Shows top 5 most recent threats.
 */
import { Link } from 'react-router-dom'
import SeverityBadge from './SeverityBadge'
import TimeAgo from './TimeAgo'
import PinButton from './PinButton'
import { useApi } from '../hooks/useApi'
import { getDisplayName } from '../displayNames'

export default function ThreatFeed() {
  const { data, loading } = useApi('/api/anomalies?limit=5&severity=CRITICAL', { poll: 30000 })
  const { data: highData } = useApi('/api/anomalies?limit=5&severity=HIGH', { poll: 30000 })

  const criticals = data?.data || []
  const highs = highData?.data || []

  // Merge and sort by detected_at descending, take top 5
  const threats = [...criticals, ...highs]
    .sort((a, b) => b.detected_at - a.detected_at)
    .slice(0, 5)

  if (loading && threats.length === 0) {
    return (
      <div className="border border-red-600/20 bg-red-600/5 p-4 mb-6">
        <div className="text-sm font-bold text-red-400 tracking-wider mb-2">LIVE THREATS</div>
        <div className="text-xs text-[#6b7280]">Scanning...</div>
      </div>
    )
  }

  if (threats.length === 0) {
    return (
      <div className="border border-[#2a2a2a] p-4 mb-6">
        <div className="flex items-center gap-2 mb-2">
          <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e]" />
          <span className="text-sm font-bold text-[#22c55e] tracking-wider">ALL CLEAR</span>
        </div>
        <div className="text-xs text-[#6b7280]">No CRITICAL or HIGH threats in the last 24 hours.</div>
      </div>
    )
  }

  return (
    <div className="border border-red-600/20 bg-red-600/5 p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
          <span className="text-sm font-bold text-red-400 tracking-wider">LIVE THREATS</span>
        </div>
        <Link to="/anomalies?severity=CRITICAL" className="text-xs text-[#f59e0b] no-underline hover:underline">
          View all &rarr;
        </Link>
      </div>
      <div className="space-y-1.5">
        {threats.map((a) => (
          <Link
            key={a.anomaly_id}
            to={`/anomalies/${a.anomaly_id}`}
            className="flex items-center gap-2 px-2 py-1.5 hover:bg-[#1a1a1a] no-underline transition-colors"
          >
            <SeverityBadge severity={a.severity} />
            <span className="text-sm text-[#e5e5e5] truncate flex-1">{getDisplayName(a)}</span>
            <PinButton
              type="anomaly"
              id={a.anomaly_id}
              label={getDisplayName(a)}
              meta={{ severity: a.severity, rule_id: a.rule_id, detected_at: a.detected_at }}
            />
            <span className="shrink-0">
              <TimeAgo timestamp={a.detected_at} />
            </span>
          </Link>
        ))}
      </div>
    </div>
  )
}
