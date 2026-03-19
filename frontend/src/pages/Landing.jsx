import { Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi'

export default function Landing() {
  const { data: health } = useApi('/api/health')
  const { data: stats } = useApi('/api/stats')

  return (
    <div className="max-w-4xl mx-auto">
      {/* Hero */}
      <div className="text-center py-10 md:py-16 px-4">
        <h1 className="text-3xl md:text-5xl font-bold tracking-wider text-[#f59e0b] mb-4">
          MONOLITH
        </h1>
        <p className="text-lg md:text-xl text-[#a3a3a3] mb-2">
          Frontier Chain Intelligence
        </p>
        <p className="text-sm text-[#6b7280] max-w-xl mx-auto px-2">
          Continuously reads Sui chain events, detects state anomalies across
          35 detection rules, and generates structured intel reports with
          on-chain evidence.
        </p>
      </div>

      {/* Live Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-12">
        <LiveStat
          label="Anomalies (24h)"
          value={stats?.anomaly_rate_24h}
        />
        <LiveStat
          label="CRITICAL"
          value={stats?.by_severity?.CRITICAL || 0}
          color="#ef4444"
        />
        <LiveStat
          label="Objects Tracked"
          value={health?.row_counts?.objects}
        />
        <LiveStat
          label="Chain Events"
          value={health?.row_counts?.chain_events}
        />
      </div>

      {/* What It Does */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
        <FeatureCard
          title="Detect"
          description="35 detection rules across 17 checkers. Pure deterministic logic — no ML, no guesswork. Rules are auditable and reproducible."
          link="/anomalies"
          linkText="View Anomaly Feed"
        />
        <FeatureCard
          title="Report"
          description="Structured bug reports with chain evidence, transaction hashes, reproduction context, and LLM plain English summaries."
          link="/anomalies"
          linkText="View Reports"
        />
        <FeatureCard
          title="Track"
          description="Paste any object ID — smart assembly, character, item — and see its complete chain history with anomalies highlighted."
          link="/submit"
          linkText="Submit a Bug"
        />
      </div>

      {/* How It Works */}
      <div className="border border-[#2a2a2a] p-6 mb-12">
        <h2 className="text-lg font-bold text-[#f59e0b] mb-4">How It Works</h2>
        <div className="space-y-3 text-sm text-[#a3a3a3]">
          <Step n={1} text="Ingestion layer polls Sui chain events via suix_queryEvents every 30 seconds" />
          <Step n={2} text="State snapshotter computes deltas between consecutive API snapshots" />
          <Step n={3} text="Detection engine runs 33 rules across 17 checkers: continuity, economic, assembly, sequence, killmail, behavioral, and more" />
          <Step n={4} text="Anomalies are scored, deduplicated (24h window), and persisted with self-contained evidence" />
          <Step n={5} text="Report generator builds formatted bug reports with chain references and investigation steps" />
          <Step n={6} text="CRITICAL/HIGH anomalies fire Discord alerts immediately" />
        </div>
      </div>

      {/* Detection Rules */}
      <div className="border border-[#2a2a2a] p-6 mb-12">
        <h2 className="text-lg font-bold text-[#f59e0b] mb-4">Detection Rules</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
          <RuleRow id="C1" name="Ghost Signal" severity="MEDIUM" />
          <RuleRow id="C2" name="Lazarus Event" severity="CRITICAL" />
          <RuleRow id="C3" name="Missing Trajectory" severity="HIGH" />
          <RuleRow id="C4" name="Dead Drift" severity="MEDIUM" />
          <RuleRow id="E1" name="Phantom Ledger" severity="HIGH" />
          <RuleRow id="E2" name="Vanishing Act" severity="HIGH" />
          <RuleRow id="E3" name="Double Stamp" severity="CRITICAL" />
          <RuleRow id="E4" name="Negative Mass" severity="CRITICAL" />
          <RuleRow id="A1" name="Forked State" severity="HIGH" />
          <RuleRow id="A2" name="Toll Runner" severity="HIGH" />
          <RuleRow id="A3" name="Gate Tax Lost" severity="MEDIUM" />
          <RuleRow id="A4" name="Shadow Inventory" severity="HIGH" />
          <RuleRow id="A5" name="Silent Seizure" severity="CRITICAL" />
          <RuleRow id="S2" name="Event Storm" severity="CRITICAL" />
          <RuleRow id="S4" name="Blind Spot" severity="MEDIUM" />
          <RuleRow id="P1" name="Chain Divergence" severity="CRITICAL" />
          <RuleRow id="K1" name="Double Tap" severity="HIGH" />
          <RuleRow id="K2" name="Witness Report" severity="MEDIUM" />
          <RuleRow id="CB1" name="Convoy Forming" severity="MEDIUM" />
          <RuleRow id="CB2" name="Fleet Mobilization" severity="CRITICAL" />
          <RuleRow id="OV1" name="State Rollback" severity="CRITICAL" />
          <RuleRow id="OV2" name="Unauthorized Mod" severity="HIGH" />
          <RuleRow id="WC1" name="Resource Baron" severity="HIGH" />
          <RuleRow id="CC1" name="Contract Tamper" severity="CRITICAL" />
          <RuleRow id="IA1" name="Matter Violation" severity="CRITICAL" />
          <RuleRow id="BP1" name="Drone Signature" severity="MEDIUM" />
          <RuleRow id="TH1" name="Drifter" severity="MEDIUM" />
          <RuleRow id="ES1" name="Orphaned Kill" severity="HIGH" />
          <RuleRow id="ES2" name="Phantom Kill" severity="CRITICAL" />
          <RuleRow id="DA1" name="Derelict" severity="LOW" />
          <RuleRow id="EV1" name="Gold Rush" severity="HIGH" />
          <RuleRow id="EV2" name="Market Silence" severity="MEDIUM" />
          <RuleRow id="OC1" name="Title Deed Transfer" severity="MEDIUM" />
        </div>
      </div>

      {/* For Judges */}
      <div className="border border-[#2a2a2a] p-6 mb-12 bg-[#111111]">
        <h2 className="text-lg font-bold text-[#f59e0b] mb-3">For Hackathon Judges</h2>
        <p className="text-sm text-[#a3a3a3] mb-4">
          The Sui migration is the hardest thing CCP has done technically. Monolith is a
          QA tool for that migration. Every bug it finds before launch is a player who
          doesn't lose their assets to a contract error.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 sm:gap-4">
          <Link to="/anomalies" className="bg-[#f59e0b] text-black px-4 py-2.5 text-sm font-bold no-underline hover:bg-[#d97706] text-center">
            View Live Feed
          </Link>
          <Link to="/stats" className="border border-[#2a2a2a] text-[#e5e5e5] px-4 py-2.5 text-sm no-underline hover:bg-[#1a1a1a] text-center">
            System Health
          </Link>
        </div>
      </div>

      {/* Footer */}
      <div className="text-center text-xs text-[#6b7280] pb-8 border-t border-[#2a2a2a] pt-6">
        <p>MONOLITH — Frontier Chain Intelligence</p>
        <p className="mt-1">
          Built by{' '}
          <a href="https://github.com/AreteDriver" className="text-[#f59e0b] hover:underline" target="_blank" rel="noopener noreferrer">
            AreteDriver
          </a>
          {' '}for the EVE Frontier x Sui Hackathon 2026
        </p>
      </div>
    </div>
  )
}

function LiveStat({ label, value, color }) {
  return (
    <div className="bg-[#111111] border border-[#2a2a2a] p-4 text-center">
      <div className="text-xs text-[#6b7280] uppercase">{label}</div>
      <div className="text-2xl font-bold mt-1 mono" style={color ? { color } : {}}>
        {value?.toLocaleString() ?? '...'}
      </div>
    </div>
  )
}

function FeatureCard({ title, description, link, linkText }) {
  return (
    <div className="border border-[#2a2a2a] p-5">
      <h3 className="text-[#f59e0b] font-bold mb-2">{title}</h3>
      <p className="text-sm text-[#a3a3a3] mb-3">{description}</p>
      <Link to={link} className="text-[#f59e0b] text-sm hover:underline no-underline">
        {linkText} &rarr;
      </Link>
    </div>
  )
}

function Step({ n, text }) {
  return (
    <div className="flex gap-3">
      <span className="text-[#f59e0b] font-bold w-6 shrink-0">{n}.</span>
      <span>{text}</span>
    </div>
  )
}

function RuleRow({ id, name, severity }) {
  const colors = {
    CRITICAL: 'text-red-400',
    HIGH: 'text-orange-400',
    MEDIUM: 'text-yellow-400',
  }
  return (
    <div className="flex items-center gap-2">
      <span className="mono text-[#f59e0b] w-8">{id}</span>
      <span className="text-[#e5e5e5]">{name}</span>
      <span className={`ml-auto text-xs font-bold ${colors[severity] || ''}`}>
        {severity}
      </span>
    </div>
  )
}
