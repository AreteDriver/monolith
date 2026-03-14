import { lazy, Suspense } from 'react'
import { Analytics } from '@vercel/analytics/react'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import AnomalyDetail from './pages/AnomalyDetail'
import AnomalyFeed from './pages/AnomalyFeed'
import Landing from './pages/Landing'
import ObjectTracker from './pages/ObjectTracker'
import ReportView from './pages/ReportView'
import SubmitPage from './pages/SubmitPage'
import AegisEcosystem from './components/AegisEcosystem'

const StatsPanel = lazy(() => import('./pages/StatsPanel'))
const MapView = lazy(() => import('./pages/MapView'))

function Nav() {
  return (
    <nav className="border-b border-[#2a2a2a] bg-[#111111] px-6 py-3 flex items-center gap-6">
      <Link to="/" className="text-[#f59e0b] font-bold text-lg tracking-wider no-underline">
        MONOLITH
      </Link>
      <Link to="/anomalies" className="text-[#a3a3a3] hover:text-white text-sm no-underline">
        Anomalies
      </Link>
      <Link to="/stats" className="text-[#a3a3a3] hover:text-white text-sm no-underline">
        Stats
      </Link>
      <Link to="/map" className="text-[#a3a3a3] hover:text-white text-sm no-underline">
        Map
      </Link>
      <Link to="/submit" className="text-[#a3a3a3] hover:text-white text-sm no-underline">
        Submit Bug
      </Link>
    </nav>
  )
}

const SuspenseFallback = <div className="text-[#a3a3a3] p-6">Loading...</div>

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav />
        <main className="max-w-7xl mx-auto px-6 py-6">
          <Suspense fallback={SuspenseFallback}>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/anomalies" element={<AnomalyFeed />} />
              <Route path="/anomalies/:id" element={<AnomalyDetail />} />
              <Route path="/reports/:id" element={<ReportView />} />
              <Route path="/objects/:id" element={<ObjectTracker />} />
              <Route path="/stats" element={<StatsPanel />} />
              <Route path="/map" element={<MapView />} />
              <Route path="/submit" element={<SubmitPage />} />
            </Routes>
          </Suspense>
        </main>
        <div className="max-w-7xl mx-auto px-6 pb-8">
          <AegisEcosystem />
        </div>
        <footer className="border-t border-[#2a2a2a] px-6 py-4 mt-8">
          <div className="max-w-7xl mx-auto text-center text-xs text-[#6b7280] space-y-1">
            <div>Monolith — Blockchain Integrity Monitor — EVE Frontier Hackathon 2026</div>
            <div style={{ fontFamily: "'Share Tech Mono', monospace", color: '#7F77DD', letterSpacing: '0.15em' }}>
              POWERED BY AEGIS STACK
            </div>
          </div>
        </footer>
      </div>
      <Analytics />
    </BrowserRouter>
  )
}
