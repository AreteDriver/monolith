const COLORS = {
  CRITICAL: 'bg-red-600 text-white',
  HIGH: 'bg-orange-500 text-white',
  MEDIUM: 'bg-yellow-500 text-black',
  LOW: 'bg-gray-600 text-white',
}

export default function SeverityBadge({ severity }) {
  const cls = COLORS[severity] || COLORS.LOW
  return (
    <span className={`${cls} px-2 py-0.5 text-xs font-bold uppercase tracking-wider`}>
      {severity}
    </span>
  )
}
