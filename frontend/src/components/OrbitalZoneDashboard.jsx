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
  LOW: 'bg-green-900/50 text-green-400 border-green-700',
  MEDIUM: 'bg-yellow-900/50 text-yellow-400 border-yellow-700',
  HIGH: 'bg-orange-900/50 text-orange-400 border-orange-700',
  CRITICAL: 'bg-red-900/50 text-red-400 border-red-700',
  UNKNOWN: 'bg-gray-900/50 text-gray-400 border-gray-700',
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
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/orbital-zones`)
      .then(r => {
        if (!r.ok) return { data: [] }
        return r.json()
      })
      .then(data => {
        const z = Array.isArray(data?.data) ? data.data
          : Array.isArray(data) ? data
          : []
        const order = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, UNKNOWN: 4 }
        z.sort((a, b) => (order[a?.threat_level] ?? 5) - (order[b?.threat_level] ?? 5))
        setZones(z)
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-[#a3a3a3] text-sm">Loading orbital zones...</div>
  if (error) return <div className="text-red-400 text-sm">Zones error: {error}</div>
  if (zones.length === 0) return (
    <div className="border border-[#2a2a2a] bg-[#111111] p-4">
      <h3 className="text-[#f59e0b] font-bold text-sm tracking-wider mb-3">ORBITAL ZONES</h3>
      <div className="text-[#6b7280] text-sm">No orbital zone data available.</div>
    </div>
  )

  return (
    <div className="border border-[#2a2a2a] bg-[#111111] p-4">
      <h3 className="text-[#f59e0b] font-bold text-sm tracking-wider mb-3">ORBITAL ZONES</h3>
      <div className="space-y-2 max-h-80 overflow-y-auto">
        {zones.map((zone, i) => {
          const threat = (zone.threat_level || 'UNKNOWN').toUpperCase()
          const stale = stalenessWarning(zone.last_polled)
          const tierColor = TIER_COLORS[zone.feral_ai_tier] || TIER_COLORS[0]
          const badgeCls = THREAT_BADGE[threat] || THREAT_BADGE.UNKNOWN
          return (
            <div key={zone.zone_id || i} className="flex items-center justify-between border-b border-[#1a1a1a] pb-2">
              <div className="flex items-center gap-3">
                <span className={`text-xs px-2 py-0.5 border ${badgeCls}`}>
                  {threat}
                </span>
                <span className="text-white text-sm">{zone.zone_name || zone.zone_id || 'Unknown'}</span>
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
