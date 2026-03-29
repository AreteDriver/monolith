import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import OrbitalZoneDashboard from '../components/OrbitalZoneDashboard'
import FeralAIEventFeed from '../components/FeralAIEventFeed'

const API_BASE = import.meta.env.VITE_API_URL || ''

export default function ZonesPage() {
  const [cycle, setCycle] = useState(null)
  const [threats, setThreats] = useState([])

  useEffect(() => {
    fetch(`${API_BASE}/api/orbital-zones/cycle`)
      .then(r => r.ok ? r.json() : null)
      .then(setCycle)
      .catch(() => setCycle(null))

    fetch(`${API_BASE}/api/orbital-zones/threats`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        const t = data?.data
        setThreats(Array.isArray(t) ? t : [])
      })
      .catch(() => setThreats([]))
  }, [])

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-white text-xl font-bold tracking-wider">ORBITAL ZONES</h1>
        <Link to="/map" className="text-xs text-[#f59e0b] no-underline hover:underline">
          View on Map
        </Link>
      </div>

      {/* Cycle + Threat Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {cycle && (
          <>
            <SummaryCard label="Cycle" value={`${cycle.cycle} — ${cycle.name}`} />
            <SummaryCard label="Day" value={cycle.days_elapsed} />
          </>
        )}
        {Array.isArray(threats) && threats.length > 0 ? (
          threats.map(t => (
            <SummaryCard
              key={t.threat_level}
              label={t.threat_level}
              value={`${t.count} zones`}
              sub={`Avg tier ${(t.avg_tier || 0).toFixed(1)}`}
            />
          ))
        ) : (
          <SummaryCard label="Threats" value="No zone data" sub="Zones populate from chain events" />
        )}
      </div>

      {/* Main panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <OrbitalZoneDashboard />
        <FeralAIEventFeed />
      </div>
    </div>
  )
}

function SummaryCard({ label, value, sub }) {
  return (
    <div className="bg-[#111111] border border-[#2a2a2a] p-3">
      <div className="text-xs text-[#6b7280] uppercase">{label}</div>
      <div className="text-sm font-bold text-white mt-1">{value}</div>
      {sub && <div className="text-xs text-[#6b7280] mt-0.5">{sub}</div>}
    </div>
  )
}
