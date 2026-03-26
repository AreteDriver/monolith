/**
 * Pinned Intel panel — shows all pinned items on the dashboard.
 * Grouped by type (anomalies, systems, filters).
 */
import { Link } from 'react-router-dom'
import { usePins } from '../hooks/usePins'
import SeverityBadge from './SeverityBadge'
import TimeAgo from './TimeAgo'

const TYPE_LABELS = {
  anomaly: 'PINNED ANOMALIES',
  system: 'PINNED SYSTEMS',
  filter: 'SAVED FILTERS',
}

export default function PinnedIntel() {
  const { pins, removePin } = usePins()

  if (pins.length === 0) return null

  const groups = {}
  for (const pin of pins) {
    const key = pin.type || 'other'
    if (!groups[key]) groups[key] = []
    groups[key].push(pin)
  }

  return (
    <div className="border border-[#f59e0b]/20 bg-[#f59e0b]/5 p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-bold text-[#f59e0b] tracking-wider">PINNED INTEL</h2>
        <span className="text-xs text-[#6b7280]">{pins.length} item{pins.length !== 1 ? 's' : ''}</span>
      </div>

      {Object.entries(groups).map(([type, items]) => (
        <div key={type} className="mb-3 last:mb-0">
          <div className="text-xs text-[#6b7280] uppercase mb-1.5 tracking-wider">
            {TYPE_LABELS[type] || type.toUpperCase()}
          </div>
          <div className="space-y-1">
            {items.map((pin) => (
              <PinnedItem key={`${pin.type}-${pin.id}`} pin={pin} onRemove={removePin} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function PinnedItem({ pin, onRemove }) {
  const linkTo = pin.type === 'anomaly'
    ? `/anomalies/${pin.id}`
    : pin.type === 'system'
    ? `/map?q=${encodeURIComponent(pin.label || pin.id)}`
    : '/anomalies'

  return (
    <div className="flex items-center gap-2 group">
      <Link
        to={linkTo}
        className="flex items-center gap-2 flex-1 px-2 py-1.5 hover:bg-[#1a1a1a] no-underline transition-colors min-w-0"
      >
        {pin.severity && <SeverityBadge severity={pin.severity} />}
        <span className="text-sm text-[#e5e5e5] truncate">{pin.label || pin.id}</span>
        {pin.rule_id && (
          <span className="mono text-xs text-[#f59e0b] shrink-0">{pin.rule_id}</span>
        )}
        {pin.detected_at && (
          <span className="ml-auto shrink-0">
            <TimeAgo timestamp={pin.detected_at} />
          </span>
        )}
      </Link>
      <button
        onClick={(e) => {
          e.preventDefault()
          onRemove(pin.type, pin.id)
        }}
        className="bg-transparent border-none cursor-pointer text-[#6b7280] hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity p-1 text-xs shrink-0"
        title="Unpin"
      >
        &#x2715;
      </button>
    </div>
  )
}
