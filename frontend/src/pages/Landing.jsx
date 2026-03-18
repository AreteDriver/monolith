import { Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi'

export default function Landing() {
  const { data: health } = useApi('/api/health')
  const { data: stats } = useApi('/api/stats')

  return (
    <div className="max-w-4xl mx-auto">
      {/* Hero */}
      <div className="text-center py-16">
        <h1 className="text-5xl font-bold tracking-wider text-[#f59e0b] mb-4">
          MONOLITH
        </h1>
        <p className="text-xl text-[#a3a3a3] mb-2">
          Blockchain Integrity Monitor for EVE Frontier
        </p>
        <p className="text-sm text-[#6b7280] max-w-xl mx-auto">
          Continuously reads Sui chain events, detects state anomalies that
          indicate bugs, and generates structured bug reports with on-chain evidence.
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
          description="17 detection rules across 4 checkers. Pure deterministic logic — no ML, no guesswork. Rules are auditable and reproducible."
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
          <Step n={3} text="Detection engine runs 17 rules: continuity, economic, assembly, and sequence checks" />
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
          <RuleRow id="A4" name="Shadow Inventory" severity="HIGH" />
          <RuleRow id="A5" name="Silent Seizure" severity="CRITICAL" />
          <RuleRow id="S2" name="Event Storm" severity="MEDIUM" />
          <RuleRow id="S4" name="Blind Spot" severity="MEDIUM" />
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
        <div className="flex gap-4">
          <Link to="/anomalies" className="bg-[#f59e0b] text-black px-4 py-2 text-sm font-bold no-underline hover:bg-[#d97706]">
            View Live Feed
          </Link>
          <Link to="/stats" className="border border-[#2a2a2a] text-[#e5e5e5] px-4 py-2 text-sm no-underline hover:bg-[#1a1a1a]">
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
