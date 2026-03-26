import { useEffect, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || ''

export default function CycleBanner() {
  const [cycle, setCycle] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/orbital-zones/cycle`)
      .then(r => r.ok ? r.json() : null)
      .then(data => data && setCycle(data))
      .catch(() => {})
  }, [])

  if (!cycle) return null

  const dayNum = cycle.day_number || cycle.dayNumber || '?'
  const cycleName = cycle.cycle_name || cycle.cycleName || 'UNKNOWN'
  const cycleNum = cycle.cycle_number || cycle.cycleNumber || '?'

  return (
    <div className="border border-[#f59e0b]/30 bg-[#f59e0b]/5 px-4 py-2 mb-4 text-center">
      <span className="text-[#f59e0b] font-bold tracking-[0.2em] text-sm" style={{ fontFamily: "'Share Tech Mono', monospace" }}>
        CYCLE {cycleNum} // {cycleName.toUpperCase()} // DAY {dayNum}
      </span>
    </div>
  )
}
