import { useEffect, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || ''

const TIER_COLORS = {
  0: 'text-gray-500',
  1: 'text-green-400',
  2: 'text-yellow-400',
  3: 'text-orange-400',
  4: 'text-red-500',
  5: 'text-red-600 font-bold',
}

const THREAT_BADGE = {
  low: 'bg-green-900/50 text-green-400 border-green-700',
  medium: 'bg-yellow-900/50 text-yellow-400 border-yellow-700',
  high: 'bg-orange-900/50 text-orange-400 border-orange-700',
  critical: 'bg-red-900/50 text-red-400 border-red-700',
}

function stalenessWarning(lastPolled) {
  if (!lastPolled) return 'NO DATA'
  const age = Math.floor(Date.now() / 1000) - lastPolled
  if (age > 1200) return `STALE (${Math.floor(age / 60)}m ago)`
  return null
}

export default function OrbitalZoneDashboard() {
  const [zones, setZones] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API_BASE}/api/orbital-zones`)
      .then(r => r.ok ? r.json() : { zones: [] })
      .then(data => {
        const z = data.zones || data || []
        // Sort by threat: critical > high > medium > low
        const order = { critical: 0, high: 1, medium: 2, low: 3, '': 4 }
        z.sort((a, b) => (order[a.threat_level] ?? 4) - (order[b.threat_level] ?? 4))
        setZones(z)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-[#a3a3a3] text-sm">Loading orbital zones...</div>
  if (zones.length === 0) return <div className="text-[#6b7280] text-sm">No orbital zone data available.</div>

  return (
    <div className="border border-[#2a2a2a] bg-[#111111] p-4">
      <h3 className="text-[#f59e0b] font-bold text-sm tracking-wider mb-3">ORBITAL ZONES</h3>
      <div className="space-y-2 max-h-80 overflow-y-auto">
        {zones.map(zone => {
          const stale = stalenessWarning(zone.last_polled)
          const tierColor = TIER_COLORS[zone.feral_ai_tier] || TIER_COLORS[0]
          const badgeCls = THREAT_BADGE[zone.threat_level] || THREAT_BADGE.low
          return (
            <div key={zone.zone_id} className="flex items-center justify-between border-b border-[#1a1a1a] pb-2">
              <div className="flex items-center gap-3">
                <span className={`text-xs px-2 py-0.5 border ${badgeCls}`}>
                  {(zone.threat_level || 'unknown').toUpperCase()}
                </span>
                <span className="text-white text-sm">{zone.zone_name || zone.zone_id}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs ${tierColor}`}>T{zone.feral_ai_tier || 0}</span>
                {stale && <span className="text-xs text-red-400 animate-pulse">{stale}</span>}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
