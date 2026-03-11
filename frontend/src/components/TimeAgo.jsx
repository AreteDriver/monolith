export default function TimeAgo({ timestamp }) {
  if (!timestamp) return <span className="text-[#6b7280]">—</span>

  const now = Math.floor(Date.now() / 1000)
  const diff = now - timestamp

  let text
  if (diff < 60) text = `${diff}s ago`
  else if (diff < 3600) text = `${Math.floor(diff / 60)}m ago`
  else if (diff < 86400) text = `${Math.floor(diff / 3600)}h ago`
  else text = `${Math.floor(diff / 86400)}d ago`

  const iso = new Date(timestamp * 1000).toISOString()

  return <span className="text-[#a3a3a3] text-sm" title={iso}>{text}</span>
}
