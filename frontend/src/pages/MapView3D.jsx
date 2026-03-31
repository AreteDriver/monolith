/**
 * MapView3D — EVE Frontier-style 3D galaxy map.
 *
 * All 24K systems as a galaxy disc with realistic thickness, bloom
 * post-processing on anomaly markers, space gradient background,
 * OrbitControls for user interaction. Anomaly systems glow bright
 * against the dim galaxy field.
 */
import { useCallback, useEffect, useState, useRef, useMemo, Suspense } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Canvas, useFrame } from '@react-three/fiber'
import { Points, PointMaterial, Html, OrbitControls, Stars } from '@react-three/drei'
import { EffectComposer, Bloom } from '@react-three/postprocessing'
import * as THREE from 'three'
import { useApi } from '../hooks/useApi'
import { getDisplayName } from '../displayNames'

const SEVERITY_COLORS = {
  critical: '#ff4444',
  high: '#ff8800',
  medium: '#ffcc00',
  low: '#6b7280',
}

function getMaxSeverity(sys) {
  if (sys.critical > 0) return 'critical'
  if (sys.high > 0) return 'high'
  if (sys.medium > 0) return 'medium'
  return 'low'
}

// Galaxy disc — all 24K systems with realistic disc thickness
function GalaxyField({ positions }) {
  const ref = useRef()

  if (!positions || positions.length === 0) return null

  return (
    <Points ref={ref} positions={positions} stride={3}>
      <PointMaterial
        transparent
        color="#8899aa"
        size={0.12}
        sizeAttenuation
        depthWrite={false}
        opacity={0.4}
      />
    </Points>
  )
}

// Anomaly marker — emissive sphere that triggers bloom
function AnomalyMarker({ position, system, onHover, onClick }) {
  const glowRef = useRef()
  const severity = getMaxSeverity(system)
  const color = SEVERITY_COLORS[severity]
  const radius = Math.max(0.3, Math.min(1.5, Math.sqrt(system.count) * 0.35))
  const isHot = severity === 'critical' || severity === 'high'

  useFrame(({ clock }) => {
    if (glowRef.current && isHot) {
      const pulse = 1 + Math.sin(clock.elapsedTime * 2 + system.count) * 0.2
      glowRef.current.scale.setScalar(pulse)
    }
  })

  const name = system.name || system.system_id?.slice(0, 10)

  return (
    <group position={position}>
      {/* Bloom-triggering emissive core */}
      <mesh ref={glowRef}
        onPointerOver={(e) => { e.stopPropagation(); onHover(system) }}
        onPointerOut={() => onHover(null)}
        onClick={(e) => { e.stopPropagation(); onClick(system) }}
      >
        <sphereGeometry args={[radius, 16, 16]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={isHot ? 3 : 1.5}
          toneMapped={false}
        />
      </mesh>
      {/* Soft outer halo */}
      <mesh>
        <sphereGeometry args={[radius * 2.5, 16, 16]} />
        <meshBasicMaterial color={color} transparent opacity={0.04} side={THREE.BackSide} />
      </mesh>
      {/* Label */}
      {(system.count >= 2 || severity === 'critical') && (
        <Html
          position={[radius + 0.5, 0.3, 0]}
          style={{ pointerEvents: 'none', whiteSpace: 'nowrap' }}
          distanceFactor={25}
        >
          <div style={{
            fontFamily: 'monospace',
            fontSize: 10,
            color: color,
            textShadow: `0 0 6px ${color}, 0 0 12px rgba(0,0,0,0.9)`,
            opacity: 0.9,
          }}>
            {name}
            <span style={{ color: '#999', marginLeft: 4, fontSize: 9 }}>{system.count}</span>
          </div>
        </Html>
      )}
    </group>
  )
}

// Ambient dust
function SpaceDust() {
  const positions = useMemo(() => {
    const p = new Float32Array(400 * 3)
    for (let i = 0; i < 400; i++) {
      p[i * 3] = (Math.random() - 0.5) * 100
      p[i * 3 + 1] = (Math.random() - 0.5) * 50
      p[i * 3 + 2] = (Math.random() - 0.5) * 100
    }
    return p
  }, [])

  return (
    <Points positions={positions} stride={3}>
      <PointMaterial transparent color="#445" size={0.1} sizeAttenuation depthWrite={false} opacity={0.3} />
    </Points>
  )
}


const SEVERITY_LABEL_COLORS = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#eab308',
  LOW: '#6b7280',
}

function timeAgo(ts) {
  const diff = Math.floor(Date.now() / 1000) - ts
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function LiveFeed() {
  const { data, loading } = useApi('/api/anomalies?limit=8', { poll: 30000 })
  const [collapsed, setCollapsed] = useState(false)
  const anomalies = data?.data || []

  return (
    <div className="absolute top-3 right-4 w-60 pointer-events-auto">
      <div className="bg-[#0a0a0a]/95 border border-[#f59e0b]/40 rounded backdrop-blur-sm">
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="w-full flex items-center justify-between px-2.5 py-1.5 border-b border-[#2a2a2a] bg-transparent cursor-pointer"
        >
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
            <span className="text-[9px] font-bold text-red-400 uppercase tracking-wider">Live Feed</span>
            {anomalies.length > 0 && (
              <span className="text-[8px] text-[#6b7280]">({anomalies.length})</span>
            )}
          </div>
          <span className="text-[#6b7280] text-[9px]">{collapsed ? '\u25bc' : '\u25b2'}</span>
        </button>
        {!collapsed && (
          <>
            <div className="max-h-[300px] overflow-y-auto">
              {loading && anomalies.length === 0 ? (
                <div className="px-2.5 py-3 text-[9px] text-[#6b7280] text-center">Scanning...</div>
              ) : anomalies.length === 0 ? (
                <div className="px-2.5 py-3 text-[9px] text-[#22c55e] text-center">All clear</div>
              ) : (
                anomalies.map((a) => (
                  <Link
                    key={a.anomaly_id}
                    to={`/anomalies/${a.anomaly_id}`}
                    className="flex items-center gap-2 px-2.5 py-1.5 hover:bg-[#1a1a1a] no-underline border-b border-[#1a1a1a] last:border-0 transition-colors"
                  >
                    <span
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{ backgroundColor: SEVERITY_LABEL_COLORS[a.severity] || '#6b7280' }}
                    />
                    <span className="text-[10px] text-[#e5e5e5] truncate flex-1">
                      {getDisplayName(a)}
                    </span>
                    <span className="text-[8px] text-[#6b7280] shrink-0">{timeAgo(a.detected_at)}</span>
                  </Link>
                ))
              )}
            </div>
            <div className="flex border-t border-[#2a2a2a]">
              <Link
                to="/anomalies"
                className="flex-1 text-center px-2.5 py-1.5 text-[9px] font-bold text-[#f59e0b] hover:text-[#fbbf24] hover:bg-[#1a1a1a] no-underline uppercase tracking-wider border-r border-[#2a2a2a] transition-colors"
              >
                View All
              </Link>
              <Link
                to="/submit"
                className="flex-1 text-center px-2.5 py-1.5 text-[9px] font-bold text-[#f59e0b] hover:text-[#fbbf24] hover:bg-[#1a1a1a] no-underline uppercase tracking-wider transition-colors"
              >
                Report
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function IntelPanel() {
  const { data: wtData } = useApi('/api/stats/map/watchtower', { poll: 60000 })
  const [collapsed, setCollapsed] = useState(false)
  const [activeTab, setActiveTab] = useState('killers')

  const killers = wtData?.top_killers || []
  const conflicts = wtData?.conflict_zones || []
  const routes = wtData?.gate_connections || []
  const territory = wtData?.territory || []
  const hotzones = wtData?.hotzones || []

  const tabs = [
    { key: 'killers', label: 'Threats', count: killers.length },
    { key: 'conflicts', label: 'War', count: conflicts.length },
    { key: 'routes', label: 'Routes', count: routes.length },
    { key: 'hotzones', label: 'Kills', count: hotzones.length },
  ]

  return (
    <div className="absolute top-[22rem] right-4 w-60 pointer-events-auto" style={{ maxHeight: 'calc(100vh - 24rem)' }}>
      <div className="bg-[#0a0a0a]/95 border border-[#2dd4bf]/40 rounded backdrop-blur-sm">
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="w-full flex items-center justify-between px-2.5 py-1.5 border-b border-[#2a2a2a] bg-transparent cursor-pointer"
        >
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#2dd4bf]" />
            <span className="text-[9px] font-bold text-[#2dd4bf] uppercase tracking-wider">Intel</span>
          </div>
          <span className="text-[#6b7280] text-[9px]">{collapsed ? '\u25bc' : '\u25b2'}</span>
        </button>
        {!collapsed && (
          <>
            <div className="flex border-b border-[#2a2a2a]">
              {tabs.map(({ key, label, count }) => (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  className={`flex-1 px-1 py-1 text-[8px] font-bold uppercase tracking-wider bg-transparent border-none cursor-pointer transition-colors ${
                    activeTab === key ? 'text-[#2dd4bf] border-b border-[#2dd4bf]' : 'text-[#6b7280] hover:text-[#a3a3a3]'
                  }`}
                  style={activeTab === key ? { borderBottom: '1px solid #2dd4bf' } : {}}
                >
                  {label}{count > 0 ? ` (${count})` : ''}
                </button>
              ))}
            </div>
            <div className="max-h-[200px] overflow-y-auto">
              {activeTab === 'killers' && (
                killers.length === 0 ? (
                  <div className="px-2.5 py-3 text-[9px] text-[#6b7280] text-center">No threat data</div>
                ) : killers.map((k) => (
                  <div key={k.entity_id} className="flex items-center gap-2 px-2.5 py-1.5 border-b border-[#1a1a1a] last:border-0">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-[10px] text-red-400 font-bold truncate">{k.display_name}</div>
                      <div className="text-[8px] text-[#6b7280]">{k.score} kills · {k.system_name}</div>
                    </div>
                  </div>
                ))
              )}
              {activeTab === 'conflicts' && (
                conflicts.length === 0 ? (
                  <div className="px-2.5 py-3 text-[9px] text-[#6b7280] text-center">No active conflicts</div>
                ) : conflicts.map((cz) => (
                  <div key={cz.system_id} className="flex items-center gap-2 px-2.5 py-1.5 border-b border-[#1a1a1a] last:border-0">
                    <span className="w-1.5 h-1.5 rounded-full bg-pink-400 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-[10px] text-pink-400 font-bold truncate">{cz.system_name}</div>
                      <div className="text-[8px] text-[#6b7280]">{cz.attacker_count} factions · {cz.total_kills} kills</div>
                    </div>
                  </div>
                ))
              )}
              {activeTab === 'routes' && (
                routes.length === 0 ? (
                  <div className="px-2.5 py-3 text-[9px] text-[#6b7280] text-center">No movement data</div>
                ) : routes.map((r, i) => (
                  <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 border-b border-[#1a1a1a] last:border-0">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#2dd4bf] shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-[10px] text-[#2dd4bf] truncate">{r.source_name} → {r.dest_name}</div>
                      <div className="text-[8px] text-[#6b7280]">{r.transits} transits</div>
                    </div>
                  </div>
                ))
              )}
              {activeTab === 'hotzones' && (
                hotzones.length === 0 ? (
                  <div className="px-2.5 py-3 text-[9px] text-[#6b7280] text-center">No kill data</div>
                ) : hotzones.slice(0, 10).map((hz) => (
                  <div key={hz.system_id} className="flex items-center gap-2 px-2.5 py-1.5 border-b border-[#1a1a1a] last:border-0">
                    <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{
                      backgroundColor: hz.danger_level === 'extreme' ? '#ff4444' : hz.danger_level === 'high' ? '#ff8800' : '#f59e0b'
                    }} />
                    <div className="flex-1 min-w-0">
                      <div className="text-[10px] text-[#e5e5e5] font-bold truncate">{hz.name}</div>
                      <div className="text-[8px] text-[#6b7280]">{hz.kills} kills · {hz.unique_attackers} attackers</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default function MapView3D() {
  const navigate = useNavigate()
  const [bgPositions, setBgPositions] = useState(null)
  const [anomalySystems, setAnomalySystems] = useState([])
  const [hovered, setHovered] = useState(null)
  const [visibleSeverities, setVisibleSeverities] = useState({
    critical: true, high: true, medium: true, low: true,
  })

  const toggleSeverity = useCallback((level) => {
    setVisibleSeverities((prev) => ({ ...prev, [level]: !prev[level] }))
  }, [])

  const { data: mapData, loading: mapLoading } = useApi('/api/stats/map', { poll: 60000 })
  const { data: bgData, refetch: refetchBg } = useApi('/api/stats/map/systems', { poll: 0 })

  // Retry until background systems load (empty on fresh deploy)
  useEffect(() => {
    if (bgData?.all_systems?.length > 0) return
    const retry = setInterval(refetchBg, 10000)
    return () => clearInterval(retry)
  }, [bgData, refetchBg])

  // All 24K systems — galaxy disc with thickness
  useEffect(() => {
    const allSystems = bgData?.all_systems || []
    if (allSystems.length === 0) return

    const positions = []
    for (const s of allSystems) {
      if (s.nx == null || s.nz == null) continue
      const x = (s.nx - 0.5) * 70
      const z = (s.nz - 0.5) * 70
      // Disc thickness — thicker near center, thinner at edges
      const distFromCenter = Math.sqrt(x * x + z * z)
      const maxThickness = 3
      const thickness = maxThickness * Math.exp(-distFromCenter * distFromCenter / 800)
      const y = (Math.random() - 0.5) * 2 * thickness
      positions.push(x, y, z)
    }
    setBgPositions(new Float32Array(positions))
  }, [bgData])

  // Anomaly markers with auto-normalized positions
  useEffect(() => {
    const systems = mapData?.systems || []
    const allSystems = bgData?.all_systems || []
    if (systems.length === 0 || allSystems.length === 0) return

    const lookup = new Map()
    for (const s of allSystems) {
      if (s.nx == null || s.nz == null) continue
      lookup.set(s.system_id, { nx: s.nx, nz: s.nz, name: s.name })
    }

    const raw = systems
      .map((sys) => {
        const coords = lookup.get(sys.system_id)
        if (!coords) return null
        return { ...sys, nx: coords.nx, nz: coords.nz, name: coords.name || sys.system_id }
      })
      .filter(Boolean)
      .sort((a, b) => a.count - b.count)

    setAnomalySystems(raw)
  }, [mapData, bgData])

  const handleClick = useCallback((system) => {
    navigate(`/anomalies?system_id=${system.system_id}`)
  }, [navigate])

  const totalAnomalies = anomalySystems.reduce((sum, s) => sum + s.count, 0)

  if (mapLoading && !bgPositions) {
    return (
      <div className="bg-[#030308] flex items-center justify-center" style={{ height: 'calc(100vh - 52px)' }}>
        <div className="flex items-center gap-2 text-[#6b7280] text-xs">
          <span className="text-[#f59e0b] animate-pulse">///</span>
          Loading galaxy...
        </div>
      </div>
    )
  }

  return (
    <div className="bg-[#030308] relative" style={{ height: 'calc(100vh - 52px)' }}>
      {/* Canvas layer — pinned behind overlays */}
      <div className="absolute inset-0" style={{ zIndex: 0 }}>
        <Canvas
          camera={{ position: [40, 25, 40], fov: 50, near: 0.1, far: 300 }}
          style={{ background: '#030308' }}
          gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.2 }}
        >
        <Suspense fallback={null}>
          <ambientLight intensity={0.2} />
          <pointLight position={[0, 30, 0]} intensity={0.5} color="#6688ff" />

          <OrbitControls
            autoRotate={false}
            enableDamping
            dampingFactor={0.05}
            minDistance={10}
            maxDistance={100}
            enablePan
            maxPolarAngle={Math.PI * 0.85}
            minPolarAngle={Math.PI * 0.15}
          />

          {/* Deep space background */}
          <Stars radius={120} depth={60} count={3000} factor={3} saturation={0.1} fade speed={0} />

          <SpaceDust />

          {/* Galaxy disc */}
          {bgPositions && <GalaxyField positions={bgPositions} />}

          {/* Anomaly markers */}
          {anomalySystems
            .filter((sys) => visibleSeverities[getMaxSeverity(sys)])
            .map((sys) => (
              <AnomalyMarker
                key={sys.system_id}
                position={[
                  (sys.nx - 0.5) * 70,
                  0,
                  ((sys.nz || 0) - 0.5) * 70,
                ]}
                system={sys}
                onHover={setHovered}
                onClick={handleClick}
              />
            ))}

          {/* Bloom post-processing */}
          <EffectComposer>
            <Bloom
              luminanceThreshold={0.8}
              luminanceSmoothing={0.3}
              intensity={1.5}
              radius={0.8}
            />
          </EffectComposer>
        </Suspense>
      </Canvas>
      </div>

      {/* UI overlay layer — sits above Canvas with pointer-events passthrough */}
      <div className="absolute inset-0 pointer-events-none" style={{ zIndex: 50 }}>

      <div className="absolute top-3 left-4 pointer-events-auto">
        <div className="text-[10px] font-bold text-[#f59e0b] uppercase tracking-wider">
          Galaxy Map
        </div>
        <div className="text-[9px] text-[#6b7280]">
          {bgPositions ? (bgPositions.length / 3).toLocaleString() : 0} systems · {totalAnomalies} anomalies
        </div>
      </div>

      <div className="absolute bottom-3 left-4 bg-[#0a0a0a]/80 border border-[#2a2a2a] rounded px-3 py-2 space-y-1 pointer-events-auto">
        <div className="text-[8px] text-[#6b7280] uppercase tracking-wider font-bold mb-1">Severity</div>
        {Object.entries(SEVERITY_COLORS).map(([level, color]) => {
          const active = visibleSeverities[level]
          const count = anomalySystems.filter((s) => getMaxSeverity(s) === level).length
          return (
            <button
              key={level}
              onClick={() => toggleSeverity(level)}
              className="flex items-center gap-2 w-full bg-transparent border-none cursor-pointer p-0 py-0.5"
            >
              <span
                className="w-2.5 h-2.5 rounded-sm border"
                style={{
                  backgroundColor: active ? color : 'transparent',
                  borderColor: color,
                  opacity: active ? 1 : 0.4,
                }}
              />
              <span className="text-[10px] uppercase font-bold" style={{ color, opacity: active ? 1 : 0.3 }}>
                {level}
              </span>
              <span className="text-[9px] ml-auto" style={{ color: active ? '#22c55e' : '#ef4444', opacity: active ? 1 : 0.6 }}>
                {active ? 'ON' : 'OFF'}
              </span>
            </button>
          )
        })}
      </div>

      <div className="absolute bottom-3 right-4 text-[9px] text-[#6b7280]">
        Drag to rotate · Scroll to zoom · Right-click to pan
      </div>

      <LiveFeed />
      <IntelPanel />

      {hovered && (
        <div className="absolute top-[17rem] right-4 bg-[#0a0a0a]/90 border border-[#2a2a2a] rounded px-3 py-2 text-xs space-y-0.5">
          <div className="font-bold text-[#e5e5e5]">{hovered.name || hovered.system_id}</div>
          <div style={{ color: SEVERITY_COLORS[getMaxSeverity(hovered)] }}>
            {getMaxSeverity(hovered).toUpperCase()} — {hovered.count} anomalies
          </div>
          {hovered.critical > 0 && <div className="text-[#ef4444]">{hovered.critical} critical</div>}
          {hovered.high > 0 && <div className="text-[#f97316]">{hovered.high} high</div>}
          <div className="text-[9px] text-[#6b7280]">Click for anomaly feed</div>
        </div>
      )}

      </div>{/* end overlay layer */}
    </div>
  )
}
