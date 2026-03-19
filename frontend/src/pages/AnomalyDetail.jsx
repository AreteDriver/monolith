import { useState, useMemo, useRef, useEffect } from 'react'
import { Link, useParams, createSearchParams } from 'react-router-dom'
import SeverityBadge from '../components/SeverityBadge'
import TimeAgo from '../components/TimeAgo'
import { useApi } from '../hooks/useApi'
import { useSystemNames, primeSystemNameCache } from '../hooks/useWatchTower'
import { getDisplayName } from '../displayNames'

const STATUS_OPTIONS = ['UNVERIFIED', 'CONFIRMED', 'FALSE_POSITIVE', 'INVESTIGATING', 'RESOLVED']

const STATUS_COLORS = {
  UNVERIFIED: '#6b7280',
  CONFIRMED: '#ef4444',
  FALSE_POSITIVE: '#22c55e',
  INVESTIGATING: '#f59e0b',
  RESOLVED: '#3b82f6',
}

export default function AnomalyDetail() {
  const { id } = useParams()
  const { data, loading } = useApi(`/api/anomalies/${id}`)
  const [generating, setGenerating] = useState(false)
  const [reportId, setReportId] = useState(null)

  if (loading) return <p className="text-[#a3a3a3]">Loading...</p>
  if (!data || data.error) return <p className="text-red-400">Anomaly not found.</p>

  const a = data

  // Prime cache with server-enriched system_name if available
  if (a.system_id && a.system_name) {
    primeSystemNameCache([a])
  }

  const systemIds = useMemo(() => a?.system_id ? [a.system_id] : [], [a?.system_id])
  const systemNames = useSystemNames(systemIds)

  async function generateReport() {
    setGenerating(true)
    try {
      const res = await fetch(`/api/reports/generate?anomaly_id=${id}`, { method: 'POST' })
      const json = await res.json()
      if (json.report_id) setReportId(json.report_id)
      else if (json.error === 'report_exists') setReportId(json.report_id)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <SeverityBadge severity={a.severity} />
        <h1 className="text-xl font-bold">{getDisplayName(a)}</h1>
        <span className="mono text-sm text-[#a3a3a3]">{a.anomaly_id}</span>
        <TimeAgo timestamp={a.detected_at} />
      </div>

      {/* Meta */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <MetaCard label="Category" value={a.category} />
        <MetaCard label="Detector" value={a.detector} />
        <MetaCard label="Rule" value={a.rule_id} />
        <StatusSelector anomalyId={a.anomaly_id} initialStatus={a.status} />
      </div>

      {/* Object */}
      <div className="border border-[#2a2a2a] p-4 mb-6">
        <h2 className="text-sm font-bold text-[#a3a3a3] mb-2">AFFECTED OBJECT</h2>
        <div className="flex flex-col sm:flex-row gap-3 sm:gap-6">
          <span className="text-sm break-all">
            <span className="text-[#6b7280]">ID: </span>
            <Link to={`/objects/${a.object_id}`} className="mono text-[#f59e0b] no-underline hover:underline">
              {a.object_id}
            </Link>
          </span>
          {a.system_id && (
            <span className="text-sm flex items-center gap-3">
              <span>
                <span className="text-[#6b7280]">System: </span>
                <a
                  href={`https://thewatchtower.xyz/system/${a.system_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mono no-underline hover:underline"
                  style={{ color: '#7F77DD' }}
                >
                  {systemNames[a.system_id] || a.system_id}
                </a>
              </span>
              <Link
                to={`/map?${createSearchParams({ q: systemNames[a.system_id] || a.system_id })}`}
                className="text-xs text-[#f59e0b] no-underline hover:underline"
              >
                View on Map
              </Link>
            </span>
          )}
        </div>
      </div>

      {/* Evidence */}
      <div className="border border-[#2a2a2a] p-4 mb-6">
        <h2 className="text-sm font-bold text-[#a3a3a3] mb-2">EVIDENCE</h2>
        <pre className="mono text-xs text-[#e5e5e5] bg-[#111111] p-4 overflow-x-auto">
          {JSON.stringify(a.evidence || JSON.parse(a.evidence_json || '{}'), null, 2)}
        </pre>
      </div>

      {/* Actions */}
      <div className="flex flex-col sm:flex-row gap-3 sm:gap-4">
        {reportId ? (
          <Link
            to={`/reports/${reportId}`}
            className="bg-[#f59e0b] text-black px-4 py-2.5 text-sm font-bold no-underline hover:bg-[#d97706] text-center"
          >
            View Report
          </Link>
        ) : (
          <button
            onClick={generateReport}
            disabled={generating}
            className="bg-[#f59e0b] text-black px-4 py-2 text-sm font-bold cursor-pointer hover:bg-[#d97706] disabled:opacity-50 border-none"
          >
            {generating ? 'Generating...' : 'Generate Bug Report'}
          </button>
        )}
        {a.report_id && !reportId && (
          <Link
            to={`/reports/${a.report_id}`}
            className="border border-[#2a2a2a] text-[#e5e5e5] px-4 py-2 text-sm no-underline hover:bg-[#1a1a1a]"
          >
            View Existing Report
          </Link>
        )}
      </div>
    </div>
  )
}

function StatusSelector({ anomalyId, initialStatus }) {
  const [status, setStatus] = useState(initialStatus || 'UNVERIFIED')
  const [updating, setUpdating] = useState(false)
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function handleClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  async function updateStatus(newStatus) {
    if (newStatus === status) {
      setOpen(false)
      return
    }
    setUpdating(true)
    setOpen(false)
    try {
      const res = await fetch(`/api/anomalies/${anomalyId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      })
      if (res.ok) {
        setStatus(newStatus)
      }
    } finally {
      setUpdating(false)
    }
  }

  const color = STATUS_COLORS[status] || '#6b7280'

  return (
    <div className="bg-[#111111] border border-[#2a2a2a] p-3 relative" ref={ref}>
      <div className="text-xs text-[#6b7280] uppercase">Status</div>
      <button
        onClick={() => setOpen(!open)}
        disabled={updating}
        className="flex items-center gap-2 mt-1 bg-transparent border-none cursor-pointer p-0 w-full"
      >
        <span
          className="w-2 h-2 rounded-full inline-block flex-shrink-0"
          style={{ backgroundColor: color }}
        />
        <span className="text-sm font-bold" style={{ color }}>
          {updating ? 'Updating...' : status}
        </span>
        <span className="text-[#6b7280] text-xs ml-auto">&#9662;</span>
      </button>
      {open && (
        <div
          className="absolute left-0 right-0 top-full mt-1 bg-[#111111] border border-[#2a2a2a] z-10"
          style={{ minWidth: '100%' }}
        >
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt}
              onClick={() => updateStatus(opt)}
              className="flex items-center gap-2 w-full px-3 py-2 bg-transparent border-none cursor-pointer hover:bg-[#1a1a1a] text-left"
            >
              <span
                className="w-2 h-2 rounded-full inline-block flex-shrink-0"
                style={{ backgroundColor: STATUS_COLORS[opt] }}
              />
              <span className="text-sm" style={{ color: STATUS_COLORS[opt] }}>
                {opt}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function MetaCard({ label, value }) {
  return (
    <div className="bg-[#111111] border border-[#2a2a2a] p-3">
      <div className="text-xs text-[#6b7280] uppercase">{label}</div>
      <div className="text-sm font-bold mt-1">{value || '\u2014'}</div>
    </div>
  )
}
