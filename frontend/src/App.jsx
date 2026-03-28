import { Component, lazy, Suspense } from 'react'
import { Analytics } from '@vercel/analytics/react'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import AnomalyDetail from './pages/AnomalyDetail'
import AnomalyFeed from './pages/AnomalyFeed'
import Landing from './pages/Landing'
import ObjectTracker from './pages/ObjectTracker'
import ReportView from './pages/ReportView'
import SubmitPage from './pages/SubmitPage'
import AegisEcosystem from './components/AegisEcosystem'
import Breadcrumbs from './components/Breadcrumbs'
import CycleBanner from './components/CycleBanner'

const ZonesPage = lazy(() => import('./pages/ZonesPage'))

const StatsPanel = lazy(() => import('./pages/StatsPanel'))
const MapView = lazy(() => import('./pages/MapView'))
const CommandCenter = lazy(() => import('./pages/CommandCenter'))
const EmbeddedView = lazy(() => import('./pages/EmbeddedView'))

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
      <Link to="/zones" className="text-[#a3a3a3] hover:text-white text-sm no-underline">
        Zones
      </Link>
      <Link to="/submit" className="text-[#a3a3a3] hover:text-white text-sm no-underline">
        Submit Bug
      </Link>
    </nav>
  )
}

const SuspenseFallback = <div className="text-[#a3a3a3] p-6">Loading...</div>

class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error) {
    return { error }
  }
  render() {
    if (this.state.error) {
      return (
        <div className="border border-red-800 bg-red-950/30 p-4 m-4 text-sm">
          <div className="text-red-400 font-bold mb-2">Something went wrong</div>
          <pre className="text-red-300 text-xs overflow-auto">{this.state.error.message}</pre>
          <button
            onClick={() => this.setState({ error: null })}
            className="mt-3 text-xs text-[#f59e0b] bg-transparent border border-[#f59e0b] px-3 py-1 cursor-pointer hover:bg-[#f59e0b] hover:text-black"
          >
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav />
        <div className="max-w-7xl mx-auto px-6 pt-4">
          <CycleBanner />
        </div>
        <Suspense fallback={SuspenseFallback}>
          <Routes>
            {/* Embedded view — no chrome, for Smart Assembly browser panels */}
            <Route path="/embed" element={<EmbeddedView />} />
            <Route path="/map" element={<CommandCenter />} />
            <Route path="*" element={
              <main className="max-w-7xl mx-auto px-6 py-6">
                <Breadcrumbs />
                <ErrorBoundary>
                  <Suspense fallback={SuspenseFallback}>
                    <Routes>
                      <Route path="/" element={<Landing />} />
                      <Route path="/anomalies" element={<AnomalyFeed />} />
                      <Route path="/anomalies/:id" element={<AnomalyDetail />} />
                      <Route path="/reports/:id" element={<ReportView />} />
                      <Route path="/objects/:id" element={<ObjectTracker />} />
                      <Route path="/stats" element={<StatsPanel />} />
                      <Route path="/zones" element={<ZonesPage />} />
                      <Route path="/submit" element={<SubmitPage />} />
                    </Routes>
                  </Suspense>
                </ErrorBoundary>
              </main>
            } />
          </Routes>
        </Suspense>
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
