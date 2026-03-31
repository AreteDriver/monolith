import { Component, lazy, Suspense } from 'react'
import { Analytics } from '@vercel/analytics/react'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import Breadcrumbs from './components/Breadcrumbs'
import CycleBanner from './components/CycleBanner'

const Landing = lazy(() => import('./pages/Landing'))
const AnomalyFeed = lazy(() => import('./pages/AnomalyFeed'))
const AnomalyDetail = lazy(() => import('./pages/AnomalyDetail'))
const ReportView = lazy(() => import('./pages/ReportView'))
const ObjectTracker = lazy(() => import('./pages/ObjectTracker'))
const SubmitPage = lazy(() => import('./pages/SubmitPage'))
const ZonesPage = lazy(() => import('./pages/ZonesPage'))
const StatsPanel = lazy(() => import('./pages/StatsPanel'))
const MapView = lazy(() => import('./pages/MapView'))
const MapView3D = lazy(() => import('./pages/MapView3D'))
const CommandCenter = lazy(() => import('./pages/CommandCenter'))
const EmbeddedView = lazy(() => import('./pages/EmbeddedView'))
const StatusPage = lazy(() => import('./pages/StatusPage'))

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
      <Link to="/map" className="text-[#a3a3a3] hover:text-white text-sm no-underline"
        onMouseEnter={() => import('./pages/MapView3D')}>
        Map
      </Link>
<Link to="/status" className="text-[#a3a3a3] hover:text-white text-sm no-underline">
        Status
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
      <Suspense fallback={SuspenseFallback}>
        <Routes>
          {/* No chrome */}
          <Route path="/embed" element={<EmbeddedView />} />

          {/* Nav only — full viewport map */}
          <Route path="/map" element={
            <div className="min-h-screen bg-[#0a0a0a]">
              <Nav />
              <MapView3D />
            </div>
          } />

          {/* Full app shell */}
          <Route path="*" element={
            <div className="min-h-screen bg-[#0a0a0a]">
              <Nav />
              <div className="max-w-7xl mx-auto px-6 pt-4">
                <CycleBanner />
              </div>
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
                      <Route path="/status" element={<StatusPage />} />
                      <Route path="/submit" element={<SubmitPage />} />
                    </Routes>
                  </Suspense>
                </ErrorBoundary>
              </main>
              <footer className="border-t border-[#2a2a2a] px-6 py-4 mt-8">
                <div className="max-w-7xl mx-auto text-center text-xs text-[#6b7280] space-y-2">
                  <div>Monolith — Blockchain Integrity Monitor — EVE Frontier Hackathon 2026</div>
                  <div className="flex items-center justify-center gap-5">
                    <a href="https://github.com/AreteDriver" target="_blank" rel="noopener noreferrer" className="text-[#6b7280] hover:text-white transition-colors" aria-label="GitHub">
                      <svg width="18" height="18" fill="currentColor" viewBox="0 0 16 16"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
                    </a>
                    <a href="https://www.linkedin.com/in/james-y-3b77b3120" target="_blank" rel="noopener noreferrer" className="text-[#6b7280] hover:text-[#0a66c2] transition-colors" aria-label="LinkedIn">
                      <svg width="18" height="18" fill="currentColor" viewBox="0 0 16 16"><path d="M13.632 13.635h-2.37V9.922c0-.886-.018-2.025-1.234-2.025-1.235 0-1.424.964-1.424 1.96v3.778h-2.37V6H8.51v1.04h.03c.318-.6 1.092-1.233 2.247-1.233 2.4 0 2.845 1.58 2.845 3.637v4.19zM3.558 4.955c-.762 0-1.376-.617-1.376-1.377 0-.758.614-1.375 1.376-1.375.76 0 1.376.617 1.376 1.375 0 .76-.616 1.377-1.376 1.377zm1.188 8.68H2.37V6h2.376v7.635zM14.816 0H1.18C.528 0 0 .516 0 1.153v13.694C0 15.484.528 16 1.18 16h13.635c.652 0 1.185-.516 1.185-1.153V1.153C16 .516 15.467 0 14.815 0z"/></svg>
                    </a>
                    <a href="https://substack.com/@aretedriver" target="_blank" rel="noopener noreferrer" className="text-[#6b7280] hover:text-[#ff6719] transition-colors" aria-label="Substack">
                      <svg width="18" height="18" fill="currentColor" viewBox="0 0 16 16"><path d="M14.4 1.6H1.6v1.8h12.8V1.6zm0 3.6H1.6v1.8h12.8V5.2zM1.6 8.8v5.6l6.4-3.2 6.4 3.2V8.8H1.6z"/></svg>
                    </a>
                    <a href="https://buymeacoffee.com/aretedriver" target="_blank" rel="noopener noreferrer" className="text-[#6b7280] hover:text-[#f59e0b] transition-colors" aria-label="Buy Me a Coffee">
                      <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M20.216 6.415l-.132-.666c-.119-.598-.388-1.163-1.001-1.379-.197-.069-.42-.098-.57-.241-.152-.143-.196-.366-.231-.572-.065-.378-.125-.756-.192-1.133-.057-.325-.102-.69-.25-.987-.195-.4-.597-.634-.996-.788a5.723 5.723 0 00-.626-.194c-1-.263-2.05-.36-3.077-.416a25.834 25.834 0 00-3.7.062c-.915.083-1.88.184-2.75.5-.318.116-.646.256-.888.501-.297.302-.393.77-.177 1.146.154.267.415.456.692.58.36.162.737.284 1.123.366 1.075.238 2.189.331 3.287.37 1.218.05 2.437.01 3.65-.118.299-.033.598-.073.896-.119.352-.054.578-.513.474-.834-.124-.383-.457-.531-.834-.473-.466.074-.96.108-1.382.146-1.177.08-2.358.082-3.536.006a22.228 22.228 0 01-1.157-.107c.402-.063.805-.112 1.21-.145 1.21-.1 2.431-.092 3.642-.009.545.037 1.091.098 1.634.169.271.036.433-.168.455-.37.023-.21-.106-.42-.31-.472l-.003-.001a18.94 18.94 0 00-2.07-.347c-1.57-.172-3.157-.107-4.712.12-.268.04-.533.093-.797.145-.263.05-.56.111-.79.285-.198.15-.308.39-.253.639.062.28.288.488.559.548l.277.056c.587.112 1.18.192 1.776.253 1.436.148 2.882.168 4.32.055.527-.041 1.053-.106 1.577-.183.34-.05.585-.404.536-.74a.625.625 0 00-.072-.196z"/><path d="M8.5 17.5c0 .828.672 1.5 1.5 1.5h4c.828 0 1.5-.672 1.5-1.5v-1H8.5v1zM16 9H8a1 1 0 00-1 1v4a4 4 0 004 4h2a4 4 0 004-4v-4a1 1 0 00-1-1zm2 1a1 1 0 011 1v1a2 2 0 01-2 2h-.5v-1.5A2.5 2.5 0 0019 10h-1z"/></svg>
                    </a>
                  </div>
                  <div style={{ fontFamily: "'Share Tech Mono', monospace", color: '#7F77DD', letterSpacing: '0.15em' }}>
                    POWERED BY AEGIS STACK
                  </div>
                </div>
              </footer>
            </div>
          } />
        </Routes>
      </Suspense>
      <Analytics />
    </BrowserRouter>
  )
}
