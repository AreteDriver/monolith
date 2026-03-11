import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import SeverityBadge from '../components/SeverityBadge'
import TimeAgo from '../components/TimeAgo'
import { useApi } from '../hooks/useApi'

export default function ObjectTracker() {
  const { id } = useParams()
  const [searchId, setSearchId] = useState('')
  const { data, loading } = useApi(`/api/objects/${id}`)

  if (loading) return <p className="text-[#a3a3a3]">Loading...</p>
  if (!data || data.error) {
    return (
      <div>
        <h1 className="text-2xl font-bold mb-4">Object Tracker</h1>
        <div className="flex gap-2 mb-6">
          <input
            type="text"
            placeholder="Paste object ID..."
            value={searchId}
            onChange={(e) => setSearchId(e.target.value)}
            className="bg-[#1a1a1a] border border-[#2a2a2a] text-[#e5e5e5] px-3 py-2 mono text-sm flex-1"
          />
          <Link
            to={`/objects/${searchId}`}
            className="bg-[#f59e0b] text-black px-4 py-2 text-sm font-bold no-underline hover:bg-[#d97706]"
          >
            Track
          </Link>
        </div>
        <p className="text-[#6b7280]">Object not found. Paste a valid object ID above.</p>
      </div>
    )
  }

  const obj = data.object
  const transitions = data.transitions || []
  const anomalies = data.anomalies || []
  const events = data.events || []

  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">Object Tracker</h1>

      {/* Object Info */}
      <div className="border border-[#2a2a2a] p-4 mb-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-[#6b7280]">ID: </span>
            <span className="mono text-[#f59e0b]">{obj.object_id}</span>
          </div>
          <div>
            <span className="text-[#6b7280]">Type: </span>
            <span>{obj.object_type || '—'}</span>
          </div>
          <div>
            <span className="text-[#6b7280]">Owner: </span>
            <span className="mono text-xs">{obj.current_owner || '—'}</span>
          </div>
          <div>
            <span className="text-[#6b7280]">System: </span>
            <span className="mono">{obj.system_id || '—'}</span>
          </div>
        </div>
      </div>

      {/* Anomalies */}
      {anomalies.length > 0 && (
        <div className="mb-6">
          <h2 className="text-sm font-bold text-[#a3a3a3] uppercase mb-3">
            Anomalies ({anomalies.length})
          </h2>
          <div className="space-y-1">
            {anomalies.map((a) => (
              <Link
                key={a.anomaly_id}
                to={`/anomalies/${a.anomaly_id}`}
                className={`block border px-3 py-2 no-underline hover:bg-[#1a1a1a] ${
                  a.severity === 'CRITICAL' ? 'border-red-600' : 'border-[#2a2a2a]'
                }`}
              >
                <div className="flex items-center gap-3">
                  <SeverityBadge severity={a.severity} />
                  <span className="mono text-sm">{a.anomaly_type}</span>
                  <span className="text-xs text-[#6b7280]">{a.rule_id}</span>
                  <span className="ml-auto"><TimeAgo timestamp={a.detected_at} /></span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* State Transitions */}
      <div className="mb-6">
        <h2 className="text-sm font-bold text-[#a3a3a3] uppercase mb-3">
          State Transitions ({transitions.length})
        </h2>
        {transitions.length === 0 ? (
          <p className="text-[#6b7280] text-sm">No transitions recorded.</p>
        ) : (
          <div className="space-y-1">
            {transitions.map((t, i) => (
              <div
                key={i}
                className={`border px-3 py-2 text-sm ${
                  t.is_valid === 0 ? 'border-red-600 bg-red-900/10' : 'border-[#2a2a2a]'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className="mono text-[#6b7280]">{t.from_state || '?'}</span>
                  <span className="text-[#f59e0b]">&rarr;</span>
                  <span className="mono">{t.to_state || '?'}</span>
                  {t.transaction_hash && (
                    <a
                      href={`https://sepolia-optimism.etherscan.io/tx/${t.transaction_hash}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mono text-xs text-[#f59e0b] hover:underline"
                    >
                      {t.transaction_hash.slice(0, 10)}...
                    </a>
                  )}
                  <span className="ml-auto"><TimeAgo timestamp={t.timestamp} /></span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Chain Events */}
      <div>
        <h2 className="text-sm font-bold text-[#a3a3a3] uppercase mb-3">
          Chain Events ({events.length})
        </h2>
        {events.length === 0 ? (
          <p className="text-[#6b7280] text-sm">No chain events recorded.</p>
        ) : (
          <div className="space-y-1">
            {events.map((e, i) => (
              <div key={i} className="border border-[#2a2a2a] px-3 py-2 text-sm">
                <div className="flex items-center gap-3">
                  <span className="mono text-[#f59e0b]">{e.event_type || '—'}</span>
                  <span className="text-[#6b7280]">block {e.block_number}</span>
                  {e.transaction_hash && (
                    <a
                      href={`https://sepolia-optimism.etherscan.io/tx/${e.transaction_hash}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mono text-xs text-[#a3a3a3] hover:underline"
                    >
                      {e.transaction_hash.slice(0, 10)}...
                    </a>
                  )}
                  <span className="ml-auto"><TimeAgo timestamp={e.timestamp} /></span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
