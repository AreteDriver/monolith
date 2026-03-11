import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useApi } from '../hooks/useApi'

const SEVERITY_COLORS = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#eab308',
  LOW: '#6b7280',
}

export default function StatsPanel() {
  const { data, loading } = useApi('/api/stats', { poll: 60000 })

  if (loading) return <p className="text-[#a3a3a3]">Loading stats...</p>
  if (!data) return <p className="text-red-400">Failed to load stats.</p>

  const severityData = Object.entries(data.by_severity || {}).map(([name, value]) => ({
    name,
    value,
  }))

  const typeData = Object.entries(data.by_type || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([name, count]) => ({ name, count }))

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">System Health</h1>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Anomalies (24h)" value={data.anomaly_rate_24h} />
        <StatCard
          label="CRITICAL"
          value={data.by_severity?.CRITICAL || 0}
          color="#ef4444"
        />
        <StatCard label="Events (24h)" value={data.events_processed_24h} />
        <StatCard label="Last Block" value={data.last_block_processed} />
      </div>

      {/* Hourly Rate Chart */}
      <div className="border border-[#2a2a2a] p-4 mb-6">
        <h2 className="text-sm font-bold text-[#a3a3a3] uppercase mb-4">
          Anomaly Rate (Last 24h)
        </h2>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={data.anomaly_rate_by_hour || []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
            <XAxis
              dataKey="hour"
              tick={{ fill: '#6b7280', fontSize: 11 }}
              tickFormatter={(h) => `${h}h`}
            />
            <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: '#1a1a1a', border: '1px solid #2a2a2a' }}
            />
            <Area
              type="monotone"
              dataKey="count"
              stroke="#f59e0b"
              fill="#f59e0b"
              fillOpacity={0.15}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        {/* Severity Pie */}
        <div className="border border-[#2a2a2a] p-4">
          <h2 className="text-sm font-bold text-[#a3a3a3] uppercase mb-4">
            By Severity
          </h2>
          {severityData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={severityData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={70}
                  label={({ name, value }) => `${name}: ${value}`}
                >
                  {severityData.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={SEVERITY_COLORS[entry.name] || '#6b7280'}
                    />
                  ))}
                </Pie>
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-[#6b7280] text-sm">No data.</p>
          )}
        </div>

        {/* Type Bar */}
        <div className="border border-[#2a2a2a] p-4">
          <h2 className="text-sm font-bold text-[#a3a3a3] uppercase mb-4">
            By Type (Top 10)
          </h2>
          {typeData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={typeData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
                <XAxis type="number" tick={{ fill: '#6b7280', fontSize: 11 }} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={180}
                  tick={{ fill: '#a3a3a3', fontSize: 10 }}
                />
                <Tooltip
                  contentStyle={{ background: '#1a1a1a', border: '1px solid #2a2a2a' }}
                />
                <Bar dataKey="count" fill="#f59e0b" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-[#6b7280] text-sm">No data.</p>
          )}
        </div>
      </div>

      {/* Top Systems */}
      {data.by_system?.length > 0 && (
        <div className="border border-[#2a2a2a] p-4 mb-6">
          <h2 className="text-sm font-bold text-[#a3a3a3] uppercase mb-3">
            Most Affected Systems
          </h2>
          <div className="space-y-1">
            {data.by_system.map((s) => (
              <div
                key={s.system_id}
                className="flex items-center gap-3 text-sm border border-[#2a2a2a] px-3 py-2"
              >
                <span className="mono text-[#f59e0b]">{s.system_id}</span>
                <div className="flex-1 bg-[#1a1a1a] h-3">
                  <div
                    className="bg-[#f59e0b] h-3"
                    style={{
                      width: `${Math.min(100, (s.count / (data.by_system[0]?.count || 1)) * 100)}%`,
                    }}
                  />
                </div>
                <span className="text-[#a3a3a3] w-8 text-right">{s.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* False Positive Rate */}
      <div className="text-xs text-[#6b7280] border-t border-[#2a2a2a] pt-4">
        False positive rate: {(data.false_positive_rate * 100).toFixed(2)}%
      </div>
    </div>
  )
}

function StatCard({ label, value, color }) {
  return (
    <div className="bg-[#111111] border border-[#2a2a2a] p-4">
      <div className="text-xs text-[#6b7280] uppercase">{label}</div>
      <div
        className="text-2xl font-bold mt-1 mono"
        style={color ? { color } : {}}
      >
        {value?.toLocaleString() ?? '—'}
      </div>
    </div>
  )
}
