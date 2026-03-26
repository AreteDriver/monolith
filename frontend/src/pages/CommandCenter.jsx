import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { AnomalyMap } from './MapView'
import SeverityBadge from '../components/SeverityBadge'
import TimeAgo from '../components/TimeAgo'
import { useApi } from '../hooks/useApi'
import { useSystemNames } from '../hooks/useWatchTower'
import { getDisplayName } from '../displayNames'

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']

export default function CommandCenter() {
  const [selectedSystem, setSelectedSystem] = useState(null)
  const [severity, setSeverity] = useState('')

  const params = new URLSearchParams({ limit: '100' })
  if (severity) params.set('severity', severity)
  if (selectedSystem) params.set('system_id', selectedSystem.system_id)

  const { data, loading } = useApi(`/api/anomalies?${params}`, { poll: 30000 })
  const anomalies = useMemo(() => data?.data || [], [data])
  const systemIds = useMemo(() => anomalies.map((a) => a.system_id), [anomalies])
  const systemNames = useSystemNames(systemIds)

  return (
    <div className="flex flex-col lg:flex-row gap-0" style={{ height: 'calc(100vh - 105px)' }}>
      {/* Map — 2/3 width */}
      <div className="lg:w-2/3 w-full relative">
        <AnomalyMap onSystemSelect={setSelectedSystem} height="100%" />
      </div>

      {/* Feed sidebar — 1/3 width */}
      <div className="lg:w-1/3 w-full border-l border-[#2a2a2a] flex flex-col bg-[#0a0a0a]">
        {/* Header */}
        <div className="px-3 py-2 border-b border-[#2a2a2a] flex items-center gap-2 shrink-0">
          <span className="text-[#f59e0b] font-bold text-xs tracking-wider">THREAT FEED</span>
          <span className="text-[#6b7280] text-xs ml-auto">{anomalies.length} signals</span>
        </div>

        {/* Filters */}
        <div className="px-3 py-2 border-b border-[#2a2a2a] flex items-center gap-2 shrink-0">
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            className="bg-[#111111] border border-[#2a2a2a] text-[#e5e5e5] px-2 py-1 text-xs flex-1"
          >
            <option value="">All</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          {selectedSystem && (
            <button
              onClick={() => setSelectedSystem(null)}
              className="text-xs bg-[#f59e0b]/20 text-[#f59e0b] border border-[#f59e0b]/30 px-2 py-1 flex items-center gap-1 cursor-pointer"
            >
              {selectedSystem.name || selectedSystem.system_id}
              <span className="text-[#6b7280]">&times;</span>
            </button>
          )}
        </div>

        {/* Scrollable feed */}
        <div className="flex-1 overflow-y-auto">
          {loading && anomalies.length === 0 && (
            <div className="text-[#6b7280] text-xs text-center py-8">Scanning chain...</div>
          )}

          {anomalies.map((a) => (
            <Link
              key={a.anomaly_id}
              to={`/anomalies/${a.anomaly_id}`}
              className={`block px-3 py-2 border-b hover:bg-[#111111] no-underline transition-colors ${
                a.severity === 'CRITICAL'
                  ? 'border-red-900/50 bg-red-950/20'
                  : 'border-[#1a1a1a]'
              }`}
            >
              <div className="flex items-center gap-2">
                <SeverityBadge severity={a.severity} />
                <span className="text-xs text-[#f59e0b] font-mono truncate flex-1">
                  {getDisplayName(a)}
                </span>
                <TimeAgo timestamp={a.detected_at} />
              </div>
              <div className="flex items-center gap-2 mt-1">
                {a.system_id && (
                  <span className="text-[10px] text-[#7F77DD]">
                    {systemNames[a.system_id] || `sys:${a.system_id}`}
                  </span>
                )}
                {a.evidence?.description && (
                  <span className="text-[10px] text-[#6b7280] truncate">
                    {a.evidence.description.length > 80
                      ? a.evidence.description.slice(0, 77) + '...'
                      : a.evidence.description}
                  </span>
                )}
              </div>
            </Link>
          ))}

          {!loading && anomalies.length === 0 && (
            <div className="text-[#6b7280] text-xs text-center py-8">
              {selectedSystem ? 'No anomalies in this system.' : 'The chain is quiet.'}
            </div>
          )}
        </div>

        {/* Footer stats */}
        <div className="px-3 py-2 border-t border-[#2a2a2a] text-[10px] text-[#6b7280] flex gap-3 shrink-0">
          <span>{anomalies.filter(a => a.severity === 'CRITICAL').length} CRIT</span>
          <span>{anomalies.filter(a => a.severity === 'HIGH').length} HIGH</span>
          <span className="ml-auto">
            <Link to="/anomalies" className="text-[#f59e0b] no-underline hover:underline">
              Full Feed &rarr;
            </Link>
          </span>
        </div>
      </div>
    </div>
  )
}
