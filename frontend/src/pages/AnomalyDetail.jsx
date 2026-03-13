import { useState, useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import SeverityBadge from '../components/SeverityBadge'
import TimeAgo from '../components/TimeAgo'
import { useApi } from '../hooks/useApi'
import { useSystemNames } from '../hooks/useWatchTower'

export default function AnomalyDetail() {
  const { id } = useParams()
  const { data, loading } = useApi(`/api/anomalies/${id}`)
  const [generating, setGenerating] = useState(false)
  const [reportId, setReportId] = useState(null)

  if (loading) return <p className="text-[#a3a3a3]">Loading...</p>
  if (!data || data.error) return <p className="text-red-400">Anomaly not found.</p>

  const a = data
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
        <h1 className="text-xl font-bold">{a.anomaly_type}</h1>
        <span className="mono text-sm text-[#a3a3a3]">{a.anomaly_id}</span>
        <TimeAgo timestamp={a.detected_at} />
      </div>

      {/* Meta */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <MetaCard label="Category" value={a.category} />
        <MetaCard label="Detector" value={a.detector} />
        <MetaCard label="Rule" value={a.rule_id} />
        <MetaCard label="Status" value={a.status} />
      </div>

      {/* Object */}
      <div className="border border-[#2a2a2a] p-4 mb-6">
        <h2 className="text-sm font-bold text-[#a3a3a3] mb-2">AFFECTED OBJECT</h2>
        <div className="flex gap-6">
          <span className="text-sm">
            <span className="text-[#6b7280]">ID: </span>
            <Link to={`/objects/${a.object_id}`} className="mono text-[#f59e0b] no-underline hover:underline">
              {a.object_id}
            </Link>
          </span>
          {a.system_id && (
            <span className="text-sm">
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
      <div className="flex gap-4">
        {reportId ? (
          <Link
            to={`/reports/${reportId}`}
            className="bg-[#f59e0b] text-black px-4 py-2 text-sm font-bold no-underline hover:bg-[#d97706]"
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

function MetaCard({ label, value }) {
  return (
    <div className="bg-[#111111] border border-[#2a2a2a] p-3">
      <div className="text-xs text-[#6b7280] uppercase">{label}</div>
      <div className="text-sm font-bold mt-1">{value || '—'}</div>
    </div>
  )
}
