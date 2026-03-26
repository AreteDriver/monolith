/**
 * Pin/unpin toggle button. Use on anomalies, systems, or filters.
 *
 * Usage: <PinButton type="anomaly" id={anomalyId} label="Forked State" meta={{severity, rule_id}} />
 */
import { usePins } from '../hooks/usePins'

export default function PinButton({ type, id, label, meta = {} }) {
  const { isPinned, addPin, removePin } = usePins()
  const pinned = isPinned(type, id)

  function toggle(e) {
    e.preventDefault()
    e.stopPropagation()
    if (pinned) {
      removePin(type, id)
    } else {
      addPin({ type, id, label, ...meta })
    }
  }

  return (
    <button
      onClick={toggle}
      className="bg-transparent border-none cursor-pointer p-1 text-sm leading-none"
      title={pinned ? 'Unpin' : 'Pin to dashboard'}
      aria-label={pinned ? `Unpin ${label}` : `Pin ${label}`}
    >
      <span style={{ color: pinned ? '#f59e0b' : '#6b7280', fontSize: '14px' }}>
        {pinned ? '\u2605' : '\u2606'}
      </span>
    </button>
  )
}
