import { useState, useMemo, useRef, useEffect } from 'react'
import { Link, useParams, createSearchParams } from 'react-router-dom'
import PinButton from '../components/PinButton'
import SeverityBadge from '../components/SeverityBadge'
import { SkeletonCard } from '../components/Skeleton'
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

  const systemId = data?.system_id
  const systemIds = useMemo(() => systemId ? [systemId] : [], [systemId])
  const systemNames = useSystemNames(systemIds)

  // Prime cache with server-enriched system_name if available
  if (data?.system_id && data?.system_name) {
    primeSystemNameCache([data])
  }

  if (loading) return (
    <div className="space-y-4">
      <SkeletonCard />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard />
      </div>
      <SkeletonCard />
    </div>
  )
  if (!data || data.error) return <p className="text-red-400">Anomaly not found.</p>

  const a = data

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
        <PinButton
          type="anomaly"
          id={a.anomaly_id}
          label={getDisplayName(a)}
          meta={{ severity: a.severity, rule_id: a.rule_id, detected_at: a.detected_at }}
        />
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

      {/* Provenance Chain */}
      {a.provenance && a.provenance.length > 0 && (
        <div className="border border-[#2a2a2a] p-4 mb-6">
          <h2 className="text-sm font-bold text-[#a3a3a3] mb-3">PROVENANCE CHAIN</h2>
          <div className="space-y-0">
            {a.provenance.map((p, i) => (
              <div key={i} className="flex items-start gap-3 relative">
                {/* Vertical connector line */}
                {i < a.provenance.length - 1 && (
                  <div className="absolute left-[7px] top-[18px] w-[2px] h-[calc(100%)] bg-[#2a2a2a]" />
                )}
                {/* Node dot */}
                <div className="w-4 h-4 rounded-full border-2 flex-shrink-0 mt-0.5"
                  style={{
                    borderColor: p.source_type === 'warden_verification' ? '#22c55e'
                      : p.source_type === 'chain_event' ? '#f59e0b'
                      : '#3b82f6',
                    backgroundColor: p.source_type === 'warden_verification' ? '#22c55e20'
                      : p.source_type === 'chain_event' ? '#f59e0b20'
                      : '#3b82f620',
                  }}
                />
                <div className="pb-4 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-bold uppercase"
                      style={{
                        color: p.source_type === 'warden_verification' ? '#22c55e'
                          : p.source_type === 'chain_event' ? '#f59e0b'
                          : '#3b82f6',
                      }}
                    >
                      {p.source_type.replace(/_/g, ' ')}
                    </span>
                    {p.timestamp > 0 && (
                      <TimeAgo timestamp={p.timestamp} />
                    )}
                  </div>
                  <p className="text-sm text-[#e5e5e5] mt-0.5">{p.derivation}</p>
                  <p className="mono text-xs text-[#6b7280] mt-0.5 break-all">
                    {p.source_id}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Warden Verdict */}
      {a.status === 'VERIFIED' && (
        <div className="border border-[#22c55e]/30 bg-[#22c55e]/5 p-4 mb-6">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#22c55e] inline-block" />
            <span className="text-sm font-bold text-[#22c55e]">WARDEN VERIFIED</span>
          </div>
          <p className="text-xs text-[#a3a3a3] mt-1">
            Autonomous verification confirmed this anomaly against on-chain state via Sui RPC.
          </p>
        </div>
      )}
      {a.status === 'DISMISSED' && (
        <div className="border border-[#6b7280]/30 bg-[#6b7280]/5 p-4 mb-6">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#6b7280] inline-block" />
            <span className="text-sm font-bold text-[#6b7280]">WARDEN DISMISSED</span>
          </div>
          <p className="text-xs text-[#a3a3a3] mt-1">
            Autonomous verification could not confirm on-chain. May be resolved or a detection artifact.
          </p>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-col sm:flex-row gap-3 sm:gap-4">
        {reportId ? (
          <Link
            to={`/reports/${reportId}`}
            className="bg-[#22c55e] text-black px-4 py-2.5 text-sm font-bold no-underline hover:bg-[#16a34a] text-center"
          >
            Reported — View Report
          </Link>
        ) : (
          <button
            onClick={generateReport}
            disabled={generating}
            className="bg-[#f59e0b] text-black px-4 py-2 text-sm font-bold cursor-pointer hover:bg-[#d97706] disabled:opacity-50 disabled:cursor-not-allowed border-none"
          >
            {generating ? 'Reporting...' : 'Generate Bug Report'}
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
