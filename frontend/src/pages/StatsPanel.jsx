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
import { getTypeName } from '../displayNames'

const SEVERITY_COLORS = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#eab308',
  LOW: '#6b7280',
}

const LEDGER_EVENT_COLORS = {
  minted: '#22c55e',
  burned: '#ef4444',
  deposited: '#3b82f6',
  withdrawn: '#f59e0b',
}

export default function StatsPanel() {
  const { data, loading } = useApi('/api/stats', { poll: 60000 })
  const { data: ledgerData, loading: ledgerLoading } = useApi('/api/stats/ledger', { poll: 60000 })

  if (loading) return <p className="text-[#a3a3a3]">Loading stats...</p>
  if (!data) return <p className="text-red-400">Failed to load stats.</p>

  const severityData = Object.entries(data.by_severity || {}).map(([name, value]) => ({
    name,
    value,
  }))

  const typeData = Object.entries(data.by_type || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([name, count]) => ({ name: getTypeName(name), count }))

  const ledgerEventData = ledgerData?.event_type_breakdown
    ? Object.entries(ledgerData.event_type_breakdown).map(([name, count]) => ({ name, count }))
    : []

  const topAssemblies = ledgerData?.top_assemblies || []

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">System Health</h1>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        <StatCard label="Anomalies (24h)" value={data.anomaly_rate_24h} />
        <StatCard
          label="CRITICAL"
          value={data.by_severity?.CRITICAL || 0}
          color="#ef4444"
        />
        <StatCard label="Events (24h)" value={data.events_processed_24h} />
        <StatCard label="Last Checkpoint" value={data.last_block_processed} />
        <StatCard
          label="POD Alerts"
          value={data.pod_anomalies_24h ?? 0}
          color="#7F77DD"
        />
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
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={severityData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="45%"
                  outerRadius={80}
                  label={({ name, value, cx: cxPos, x, y, midAngle }) => {
                    const offset = x > cxPos ? 8 : -8
                    const anchor = x > cxPos ? 'start' : 'end'
                    return (
                      <text x={x + offset} y={y} textAnchor={anchor} fill="#e5e5e5" fontSize={11}>
                        {`${name}: ${value}`}
                      </text>
                    )
                  }}
                  labelLine={{ stroke: '#6b7280', strokeWidth: 1 }}
                >
                  {severityData.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={SEVERITY_COLORS[entry.name] || '#6b7280'}
                    />
                  ))}
                </Pie>
                <Legend
                  wrapperStyle={{ fontSize: '11px', paddingTop: '8px' }}
                />
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

      {/* Item Ledger */}
      <div className="border border-[#2a2a2a] p-4 mb-6">
        <h2 className="text-sm font-bold text-[#a3a3a3] uppercase mb-4">
          Item Ledger
        </h2>
        {ledgerLoading ? (
          <p className="text-[#a3a3a3] text-sm">Loading ledger data...</p>
        ) : !ledgerData ? (
          <p className="text-[#6b7280] text-sm">No ledger data available.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-2 gap-4 mb-6">
              <StatCard label="Total Items Tracked" value={ledgerData.total_items ?? 0} />
              <StatCard label="Total Ledger Events" value={ledgerData.total_events ?? 0} />
            </div>

            {/* Event Type Breakdown */}
            {ledgerEventData.length > 0 ? (
              <div className="mb-6">
                <h3 className="text-xs text-[#6b7280] uppercase mb-3">Event Type Breakdown</h3>
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={ledgerEventData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
                    <XAxis type="number" tick={{ fill: '#6b7280', fontSize: 11 }} />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={100}
                      tick={{ fill: '#a3a3a3', fontSize: 11 }}
                    />
                    <Tooltip
                      contentStyle={{ background: '#1a1a1a', border: '1px solid #2a2a2a' }}
                    />
                    <Bar dataKey="count">
                      {ledgerEventData.map((entry) => (
                        <Cell
                          key={entry.name}
                          fill={LEDGER_EVENT_COLORS[entry.name] || '#f59e0b'}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-[#6b7280] text-sm mb-4">No event breakdown available.</p>
            )}

            {/* Top Assemblies */}
            {topAssemblies.length > 0 && (
              <div>
                <h3 className="text-xs text-[#6b7280] uppercase mb-3">Top 5 Most Active Assemblies</h3>
                <div className="space-y-1">
                  {topAssemblies.slice(0, 5).map((a, i) => (
                    <div
                      key={a.assembly_id || i}
                      className="flex items-center justify-between text-sm border border-[#2a2a2a] px-3 py-2"
                    >
                      <span className="mono text-[#f59e0b] truncate" style={{ maxWidth: '70%' }}>
                        {a.assembly_id || a.name || `Assembly ${i + 1}`}
                      </span>
                      <span className="text-[#a3a3a3] mono">{a.event_count ?? a.count ?? 0}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>

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
        {value?.toLocaleString() ?? '\u2014'}
      </div>
    </div>
  )
}
