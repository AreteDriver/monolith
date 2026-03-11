import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import AnomalyDetail from './pages/AnomalyDetail'
import AnomalyFeed from './pages/AnomalyFeed'
import ObjectTracker from './pages/ObjectTracker'
import ReportView from './pages/ReportView'
import StatsPanel from './pages/StatsPanel'
import SubmitPage from './pages/SubmitPage'

function Nav() {
  return (
    <nav className="border-b border-[#2a2a2a] bg-[#111111] px-6 py-3 flex items-center gap-6">
      <Link to="/" className="text-[#f59e0b] font-bold text-lg tracking-wider no-underline">
        MONOLITH
      </Link>
      <Link to="/" className="text-[#a3a3a3] hover:text-white text-sm no-underline">
        Anomalies
      </Link>
      <Link to="/stats" className="text-[#a3a3a3] hover:text-white text-sm no-underline">
        Stats
      </Link>
      <Link to="/submit" className="text-[#a3a3a3] hover:text-white text-sm no-underline">
        Submit Bug
      </Link>
    </nav>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav />
        <main className="max-w-7xl mx-auto px-6 py-6">
          <Routes>
            <Route path="/" element={<AnomalyFeed />} />
            <Route path="/anomalies/:id" element={<AnomalyDetail />} />
            <Route path="/reports/:id" element={<ReportView />} />
            <Route path="/objects/:id" element={<ObjectTracker />} />
            <Route path="/stats" element={<StatsPanel />} />
            <Route path="/submit" element={<SubmitPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
