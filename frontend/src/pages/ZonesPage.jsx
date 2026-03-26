import OrbitalZoneDashboard from '../components/OrbitalZoneDashboard'
import FeralAIEventFeed from '../components/FeralAIEventFeed'

export default function ZonesPage() {
  return (
    <div>
      <h2 className="text-white text-xl font-bold mb-4 tracking-wider">ORBITAL ZONES</h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <OrbitalZoneDashboard />
        <FeralAIEventFeed />
      </div>
    </div>
  )
}
