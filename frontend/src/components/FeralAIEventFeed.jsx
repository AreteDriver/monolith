import { useEffect, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || ''

function timeAgo(ts) {
  if (!ts) return ''
  const seconds = Math.floor(Date.now() / 1000) - ts
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

const SEVERITY_COLORS = {
  CRITICAL: 'text-red-500',
  HIGH: 'text-orange-400',
  MEDIUM: 'text-yellow-400',
  LOW: 'text-gray-400',
}

export default function FeralAIEventFeed() {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/orbital-zones/feral-ai/events`)
      .then(r => {
        if (!r.ok) return { data: [] }
        return r.json()
      })
      .then(data => {
        const evts = Array.isArray(data?.data) ? data.data
          : Array.isArray(data) ? data
          : []
        setEvents(evts)
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-[#a3a3a3] text-sm">Loading feral AI events...</div>
  if (error) return <div className="text-red-400 text-sm">Events error: {error}</div>
  if (events.length === 0) return (
    <div className="border border-[#2a2a2a] bg-[#111111] p-4">
      <h3 className="text-[#f59e0b] font-bold text-sm tracking-wider mb-3">FERAL AI EVENTS</h3>
      <div className="text-[#6b7280] text-sm">No feral AI events detected.</div>
    </div>
  )

  return (
    <div className="border border-[#2a2a2a] bg-[#111111] p-4">
      <h3 className="text-[#f59e0b] font-bold text-sm tracking-wider mb-3">FERAL AI EVENTS</h3>
      <div className="space-y-2 max-h-80 overflow-y-auto">
        {events.map((evt, i) => {
          const sevColor = SEVERITY_COLORS[evt?.severity] || SEVERITY_COLORS.LOW
          return (
            <div key={evt?.id || evt?.event_id || i} className="border-b border-[#1a1a1a] pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-bold ${sevColor}`}>{evt?.severity || 'LOW'}</span>
                  <span className="text-white text-sm">{evt?.event_type || evt?.type || 'Unknown'}</span>
                </div>
                <span className="text-[#6b7280] text-xs">
                  {timeAgo(evt?.detected_at)}
                </span>
              </div>
              {evt?.zone_name && (
                <div className="text-[#a3a3a3] text-xs mt-1">Zone: {evt.zone_name}</div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
