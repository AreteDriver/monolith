import { Link, useLocation } from 'react-router-dom'

const ROUTE_NAMES = {
  '': 'Dashboard',
  anomalies: 'Anomaly Feed',
  stats: 'Stats',
  map: 'Map',
  zones: 'Zones',
  submit: 'Submit Bug',
  objects: 'Object Tracker',
  reports: 'Report',
}

export default function Breadcrumbs() {
  const { pathname } = useLocation()

  if (pathname === '/') return null

  const segments = pathname.split('/').filter(Boolean)
  const crumbs = [{ label: 'Dashboard', to: '/' }]

  let path = ''
  for (const seg of segments) {
    path += `/${seg}`
    const name = ROUTE_NAMES[seg]
    if (name) {
      crumbs.push({ label: name, to: path })
    } else {
      // Dynamic segment (anomaly ID, report ID, etc.)
      crumbs.push({ label: seg.length > 20 ? seg.slice(0, 17) + '...' : seg, to: path })
    }
  }

  return (
    <nav className="text-xs text-[#6b7280] mb-3 flex items-center gap-1.5">
      {crumbs.map((c, i) => (
        <span key={c.to} className="flex items-center gap-1.5">
          {i > 0 && <span className="text-[#3a3a3a]">/</span>}
          {i < crumbs.length - 1 ? (
            <Link to={c.to} className="text-[#6b7280] hover:text-[#a3a3a3] no-underline">
              {c.label}
            </Link>
          ) : (
            <span className="text-[#a3a3a3]">{c.label}</span>
          )}
        </span>
      ))}
    </nav>
  )
}
