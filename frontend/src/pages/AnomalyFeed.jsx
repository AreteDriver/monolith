import { useState, useMemo } from 'react'
import { Link, createSearchParams } from 'react-router-dom'
import PinButton from '../components/PinButton'
import SeverityBadge from '../components/SeverityBadge'
import { SkeletonFeed } from '../components/Skeleton'
import TimeAgo from '../components/TimeAgo'
import { useApi } from '../hooks/useApi'
import { useSystemNames } from '../hooks/useWatchTower'
import { getDisplayName } from '../displayNames'

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']

function truncate(s, n) {
  if (!s) return '—'
  return s.length > n ? s.slice(0, n - 3) + '...' : s
}

export default function AnomalyFeed() {
  const [severity, setSeverity] = useState('')
  const [anomalyType, setAnomalyType] = useState('')

  const params = new URLSearchParams({ limit: '100' })
  if (severity) params.set('severity', severity)
  if (anomalyType) params.set('anomaly_type', anomalyType)

  const { data, loading } = useApi(`/api/anomalies?${params}`, { poll: 30000 })
  const anomalies = useMemo(() => data?.data || [], [data])
  const systemIds = useMemo(() => anomalies.map((a) => a.system_id), [anomalies])
  const systemNames = useSystemNames(systemIds)

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Anomaly Feed</h1>

      {/* Filters */}
      <div className="flex gap-3 mb-4">
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="bg-[#1a1a1a] border border-[#2a2a2a] text-[#e5e5e5] px-3 py-1.5 text-sm"
        >
          <option value="">All Severities</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Filter by type..."
          value={anomalyType}
          onChange={(e) => setAnomalyType(e.target.value.toUpperCase())}
          className="bg-[#1a1a1a] border border-[#2a2a2a] text-[#e5e5e5] px-3 py-1.5 text-sm w-full sm:w-48"
        />
      </div>

      {/* Feed */}
      {loading && anomalies.length === 0 && <SkeletonFeed rows={8} />}

      <div className="space-y-1">
        {anomalies.map((a) => (
          <Link
            key={a.anomaly_id}
            to={`/anomalies/${a.anomaly_id}`}
            className={`block border px-4 py-3 hover:bg-[#1a1a1a] no-underline transition-colors ${
              a.severity === 'CRITICAL'
                ? 'border-red-600 animate-pulse-critical'
                : 'border-[#2a2a2a]'
            }`}
          >
            <div className="flex flex-wrap items-center gap-2 sm:gap-4">
              <SeverityBadge severity={a.severity} />
              <span className="mono text-sm text-[#f59e0b]">{getDisplayName(a)}</span>
              <span className="mono text-xs text-[#a3a3a3] hidden sm:inline">
                {truncate(a.object_id, 20)}
              </span>
              {a.system_id && (
                <span className="flex items-center gap-2">
                  <a
                    href={`https://thewatchtower.xyz/system/${a.system_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs no-underline hover:underline"
                    style={{ color: '#7F77DD' }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {systemNames[a.system_id] || `sys:${a.system_id}`}
                  </a>
                  <Link
                    to={`/map?${createSearchParams({ q: systemNames[a.system_id] || a.system_id })}`}
                    className="text-xs text-[#f59e0b] no-underline hover:underline"
                    onClick={(e) => e.stopPropagation()}
                    title="View on Map"
                  >
                    MAP
                  </Link>
                </span>
              )}
              <span className="ml-auto flex items-center gap-1 text-nowrap">
                <PinButton
                  type="anomaly"
                  id={a.anomaly_id}
                  label={getDisplayName(a)}
                  meta={{ severity: a.severity, rule_id: a.rule_id, detected_at: a.detected_at }}
                />
                <TimeAgo timestamp={a.detected_at} />
              </span>
            </div>
            {a.evidence?.description && (
              <p className="text-xs text-[#6b7280] mt-1 ml-16">
                {truncate(a.evidence.description, 120)}
              </p>
            )}
          </Link>
        ))}
      </div>

      {!loading && anomalies.length === 0 && (
        <p className="text-[#6b7280] text-center py-12">
          No signals intercepted. The chain is quiet.
        </p>
      )}
    </div>
  )
}
