import { useSearchParams } from 'react-router-dom'

export default function MapView() {
  const [searchParams] = useSearchParams()
  const query = searchParams.get('q') || ''
  const embedUrl = query
    ? `https://ef-map.com/embed?q=${encodeURIComponent(query)}`
    : 'https://ef-map.com/embed'

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-[#f59e0b] tracking-wider">
            FRONTIER MAP
          </h1>
          {query && (
            <span className="text-xs text-[#a3a3a3] bg-[#1a1a1a] border border-[#2a2a2a] px-2 py-1 mono">
              {query}
            </span>
          )}
        </div>
        <a
          href="https://ef-map.com"
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-[#6b7280] hover:text-[#a3a3a3] no-underline"
        >
          Powered by EF-Map
        </a>
      </div>
      <div className="border border-[#2a2a2a] overflow-hidden" style={{ height: 'calc(100vh - 200px)' }}>
        <iframe
          src={embedUrl}
          title="EVE Frontier Map"
          width="100%"
          height="100%"
          style={{ border: 'none' }}
          allowFullScreen
        />
      </div>
    </div>
  )
}
