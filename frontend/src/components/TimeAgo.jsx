import { useState, useEffect } from 'react'

function formatDiff(timestamp) {
  const diff = Math.floor(Date.now() / 1000) - timestamp
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export default function TimeAgo({ timestamp }) {
  const [text, setText] = useState(() => timestamp ? formatDiff(timestamp) : null)

  useEffect(() => {
    if (!timestamp) return
    const id = setInterval(() => setText(formatDiff(timestamp)), 15000)
    return () => clearInterval(id)
  }, [timestamp])

  if (!timestamp) return <span className="text-[#6b7280]">{'\u2014'}</span>

  const iso = new Date(timestamp * 1000).toISOString()

  return <span className="text-[#a3a3a3] text-sm" title={iso}>{text}</span>
}
