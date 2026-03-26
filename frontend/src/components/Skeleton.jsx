/**
 * Loading skeleton placeholders.
 */

export function SkeletonLine({ width = '100%', height = '16px' }) {
  return (
    <div
      className="bg-[#1a1a1a] animate-pulse rounded"
      style={{ width, height }}
    />
  )
}

export function SkeletonCard() {
  return (
    <div className="bg-[#111111] border border-[#2a2a2a] p-4 space-y-2">
      <SkeletonLine width="40%" height="12px" />
      <SkeletonLine width="60%" height="24px" />
    </div>
  )
}

export function SkeletonRow() {
  return (
    <div className="border border-[#2a2a2a] px-4 py-3 flex items-center gap-4">
      <SkeletonLine width="60px" height="20px" />
      <SkeletonLine width="120px" height="16px" />
      <SkeletonLine width="80px" height="14px" />
      <div className="ml-auto">
        <SkeletonLine width="50px" height="14px" />
      </div>
    </div>
  )
}

export function SkeletonFeed({ rows = 5 }) {
  return (
    <div className="space-y-1">
      {Array.from({ length: rows }, (_, i) => (
        <SkeletonRow key={i} />
      ))}
    </div>
  )
}

export function SkeletonStats({ cards = 5 }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
      {Array.from({ length: cards }, (_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  )
}
