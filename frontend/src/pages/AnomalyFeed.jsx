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

const PAGE_SIZE = 25

export default function AnomalyFeed() {
  const [severity, setSeverity] = useState('')
  const [anomalyType, setAnomalyType] = useState('')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState(new Set())
  const [bulkStatus, setBulkStatus] = useState('')

  const params = new URLSearchParams({ limit: '200' })
  if (severity) params.set('severity', severity)
  if (anomalyType) params.set('anomaly_type', anomalyType)

  const { data, loading, refetch } = useApi(`/api/anomalies?${params}`, { poll: 30000 })
  const allAnomalies = useMemo(() => data?.data || [], [data])
  const totalPages = Math.ceil(allAnomalies.length / PAGE_SIZE)
  const anomalies = useMemo(
    () => allAnomalies.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE),
    [allAnomalies, page]
  )
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
              <input
                type="checkbox"
                checked={selected.has(a.anomaly_id)}
                onChange={(e) => {
                  e.stopPropagation()
                  setSelected(prev => {
                    const next = new Set(prev)
                    if (next.has(a.anomaly_id)) next.delete(a.anomaly_id)
                    else next.add(a.anomaly_id)
                    return next
                  })
                }}
                onClick={(e) => e.stopPropagation()}
                className="accent-[#f59e0b] cursor-pointer"
              />
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

      {/* Bulk Actions */}
      {selected.size > 0 && (
        <div className="flex items-center gap-3 mt-4 p-3 border border-[#f59e0b]/30 bg-[#f59e0b]/5">
          <span className="text-sm text-[#f59e0b] font-bold">{selected.size} selected</span>
          <select
            value={bulkStatus}
            onChange={(e) => setBulkStatus(e.target.value)}
            className="bg-[#1a1a1a] border border-[#2a2a2a] text-[#e5e5e5] px-2 py-1 text-xs"
          >
            <option value="">Set status...</option>
            <option value="CONFIRMED">CONFIRMED</option>
            <option value="FALSE_POSITIVE">FALSE_POSITIVE</option>
            <option value="INVESTIGATING">INVESTIGATING</option>
            <option value="RESOLVED">RESOLVED</option>
          </select>
          <button
            onClick={async () => {
              if (!bulkStatus) return
              await fetch('/api/anomalies/bulk/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ anomaly_ids: [...selected], status: bulkStatus }),
              })
              setSelected(new Set())
              setBulkStatus('')
              refetch()
            }}
            disabled={!bulkStatus}
            className="bg-[#f59e0b] text-black px-3 py-1 text-xs font-bold cursor-pointer border-none disabled:opacity-50"
          >
            Apply
          </button>
          <button
            onClick={() => setSelected(new Set())}
            className="text-[#6b7280] hover:text-white text-xs bg-transparent border-none cursor-pointer"
          >
            Clear
          </button>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-4 text-sm">
          <button
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0}
            className="bg-[#111111] border border-[#2a2a2a] text-[#a3a3a3] hover:text-white px-3 py-1 text-xs disabled:opacity-30 cursor-pointer disabled:cursor-default"
          >
            Prev
          </button>
          <span className="text-[#6b7280] text-xs">
            Page {page + 1} of {totalPages} ({allAnomalies.length} total)
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
            disabled={page >= totalPages - 1}
            className="bg-[#111111] border border-[#2a2a2a] text-[#a3a3a3] hover:text-white px-3 py-1 text-xs disabled:opacity-30 cursor-pointer disabled:cursor-default"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
