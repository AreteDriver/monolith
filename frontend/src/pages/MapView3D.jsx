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
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Points, PointMaterial, Html, OrbitControls, Stars, Line } from '@react-three/drei'
import { EffectComposer, Bloom } from '@react-three/postprocessing'
import * as THREE from 'three'
import { useApi } from '../hooks/useApi'
import { getDisplayName } from '../displayNames'

// Unified color palette — dark sci-fi command center
// Primary: amber (#f59e0b) — Monolith brand, UI elements
// Danger: red (#ef4444) — critical threats, kills
// Warning: orange (#f97316) — high severity
// Caution: amber (#eab308) — medium severity
// Neutral: slate (#6b7280) — low, inactive
// Intel: teal (#2dd4bf) — routes, connections, data flow
// Conflict: rose (#f43f5e) — contested zones
const SEVERITY_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#64748b',
}

function getMaxSeverity(sys) {
  if (sys.critical > 0) return 'critical'
  if (sys.high > 0) return 'high'
  if (sys.medium > 0) return 'medium'
  return 'low'
}

// Galaxy disc — systems + nebula clouds + core glow
function GalaxyField({ positions, systems, onSystemClick }) {
  const ref = useRef()

  // Click on invisible galactic plane → find nearest system
  const handlePlaneClick = useCallback((e) => {
    if (!systems || systems.length === 0) return
    e.stopPropagation()
    const point = e.point // THREE.Vector3 intersection on the plane
    const clickX = point.x
    const clickZ = point.z

    // Find nearest system within 2 units
    let nearest = null
    let nearestDist = 4 // max click distance squared
    for (const sys of systems) {
      const sx = (sys.nx - 0.5) * 70
      const sz = (sys.nz - 0.5) * 70
      const d = (clickX - sx) ** 2 + (clickZ - sz) ** 2
      if (d < nearestDist) {
        nearestDist = d
        nearest = sys
      }
    }
    if (nearest) onSystemClick(nearest)
  }, [systems, onSystemClick])

  if (!positions || positions.length === 0) return null

  return (
    <group>
      {/* Invisible click plane on galactic disc */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} onClick={handlePlaneClick} visible={false}>
        <planeGeometry args={[80, 80]} />
        <meshBasicMaterial transparent opacity={0} side={THREE.DoubleSide} />
      </mesh>

      <Points ref={ref} positions={positions} stride={3}>
        <PointMaterial
          transparent
          color="#aabbcc"
          size={0.16}
          sizeAttenuation
          depthWrite={false}
          opacity={0.55}
        />
      </Points>

      {/* Galactic core — subtle glow */}
      <mesh position={[0, 0, 0]}>
        <sphereGeometry args={[3, 16, 16]} />
        <meshBasicMaterial color="#334466" transparent opacity={0.06} />
      </mesh>

      {/* Nebula clouds — subtle, monochrome-ish */}
      <mesh position={[14, 0.3, -10]}>
        <sphereGeometry args={[8, 12, 12]} />
        <meshBasicMaterial color="#334488" transparent opacity={0.018} />
      </mesh>
      <mesh position={[-12, 0.2, 12]}>
        <sphereGeometry args={[10, 12, 12]} />
        <meshBasicMaterial color="#223366" transparent opacity={0.015} />
      </mesh>

      {/* Galactic plane grid — subtle reference */}
      <gridHelper args={[80, 40, '#1a2233', '#0d1118']} position={[0, -0.1, 0]} />
    </group>
  )
}

// Anomaly marker — emissive sphere with danger rings and halo
function AnomalyMarker({ position, system, onHover, onClick }) {
  const groupRef = useRef()
  const ringRef = useRef()
  const severity = getMaxSeverity(system)
  const color = SEVERITY_COLORS[severity]
  const radius = Math.max(0.4, Math.min(1.8, Math.sqrt(system.count) * 0.45))
  const isHot = severity === 'critical' || severity === 'high'

  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    if (groupRef.current && isHot) {
      const pulse = 1 + Math.sin(t * 2 + system.count) * 0.25
      groupRef.current.scale.setScalar(pulse)
    }
    if (ringRef.current) {
      ringRef.current.rotation.z = t * 0.5
    }
  })

  const name = system.name || system.system_id?.slice(0, 10)

  return (
    <group position={position}>
      {/* Bloom-triggering emissive core */}
      <mesh ref={groupRef}
        onPointerOver={(e) => { e.stopPropagation(); onHover(system) }}
        onPointerOut={() => onHover(null)}
        onClick={(e) => { e.stopPropagation(); onClick(system) }}
      >
        <sphereGeometry args={[radius, 16, 16]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={isHot ? 4 : 2}
          toneMapped={false}
        />
      </mesh>

      {/* Subtle halo */}
      <mesh>
        <sphereGeometry args={[radius * 2, 12, 12]} />
        <meshBasicMaterial color={color} transparent opacity={0.03} side={THREE.BackSide} />
      </mesh>

      {/* Thin danger ring for critical/high */}
      {isHot && (
        <mesh ref={ringRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]}>
          <ringGeometry args={[radius * 1.6, radius * 1.7, 24]} />
          <meshBasicMaterial color={color} transparent opacity={0.2} side={THREE.DoubleSide} />
        </mesh>
      )}

      {/* Label — only for 2+ anomalies or critical */}
      {(system.count >= 2 || severity === 'critical') && (
        <Html
          position={[radius + 0.4, 0.3, 0]}
          style={{ pointerEvents: 'none', whiteSpace: 'nowrap' }}
          distanceFactor={30}
        >
          <div style={{
            fontFamily: 'monospace',
            fontSize: 9,
            color: color,
            textShadow: `0 0 6px ${color}, 0 0 10px rgba(0,0,0,0.95)`,
            opacity: 0.8,
          }}>
            {name}
            <span style={{ color: '#999', marginLeft: 3, fontSize: 8 }}>{system.count}</span>
          </div>
        </Html>
      )}
    </group>
  )
}

// Heat map — continuous danger gradient on the galactic plane
function HeatMap({ hotzones }) {
  const meshRef = useRef()
  const materialRef = useRef()

  const { uniforms, positions: heatPositions } = useMemo(() => {
    if (!hotzones || hotzones.length === 0) {
      return { uniforms: null, positions: [] }
    }
    const maxKills = Math.max(...hotzones.map(h => h.kills), 1)
    const heatData = hotzones.slice(0, 32).map(hz => ({
      x: (hz.nx - 0.5) * 70,
      z: (hz.nz - 0.5) * 70,
      intensity: hz.kills / maxKills,
    }))

    // Pack into uniforms
    const posArray = new Float32Array(32 * 2).fill(9999)
    const intArray = new Float32Array(32).fill(0)
    heatData.forEach((h, i) => {
      posArray[i * 2] = h.x
      posArray[i * 2 + 1] = h.z
      intArray[i] = h.intensity
    })

    return {
      uniforms: {
        uHeatPos: { value: posArray },
        uHeatInt: { value: intArray },
        uCount: { value: heatData.length },
        uTime: { value: 0 },
      },
      positions: heatData,
    }
  }, [hotzones])

  useFrame(({ clock }) => {
    if (materialRef.current && uniforms) {
      materialRef.current.uniforms.uTime.value = clock.elapsedTime
    }
  })

  if (!uniforms || !heatPositions || heatPositions.length === 0) return null

  return (
    <mesh ref={meshRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
      <planeGeometry args={[80, 80, 1, 1]} />
      <shaderMaterial
        ref={materialRef}
        transparent
        depthWrite={false}
        uniforms={uniforms}
        vertexShader={`
          varying vec2 vUv;
          void main() {
            vUv = uv;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          }
        `}
        fragmentShader={`
          uniform float uHeatPos[64];
          uniform float uHeatInt[32];
          uniform int uCount;
          uniform float uTime;
          varying vec2 vUv;

          void main() {
            vec2 worldPos = (vUv - 0.5) * 80.0;
            float heat = 0.0;

            for (int i = 0; i < 32; i++) {
              float active = step(float(i) + 0.5, float(uCount));
              vec2 hPos = vec2(uHeatPos[i * 2], uHeatPos[i * 2 + 1]);
              float dist = length(worldPos - hPos);
              float falloff = uHeatInt[i] * exp(-dist * dist / 120.0);
              heat += falloff * active;
            }

            heat = clamp(heat, 0.0, 1.0);

            // Sleek color ramp: dark teal → amber → red
            vec3 cold = vec3(0.05, 0.12, 0.2);
            vec3 warm = vec3(0.85, 0.55, 0.08);
            vec3 hot = vec3(0.9, 0.12, 0.08);

            vec3 color = heat < 0.5
              ? mix(cold, warm, heat * 2.0)
              : mix(warm, hot, (heat - 0.5) * 2.0);

            float alpha = heat * 0.08;
            if (alpha < 0.003) discard;

            gl_FragColor = vec4(color, alpha);
          }
        `}
      />
    </mesh>
  )
}

// Selection beacon — ring + pin + label at selected system
function SelectionBeacon({ position, name }) {
  const ringRef = useRef()
  const beamRef = useRef()

  useFrame(({ clock }) => {
    if (ringRef.current) {
      ringRef.current.rotation.z = clock.elapsedTime * 0.8
      const pulse = 1 + Math.sin(clock.elapsedTime * 3) * 0.15
      ringRef.current.scale.setScalar(pulse)
    }
    if (beamRef.current) {
      const flicker = 0.35 + Math.sin(clock.elapsedTime * 5) * 0.15
      beamRef.current.material.opacity = flicker
    }
  })

  if (!position) return null

  return (
    <group position={position}>
      {/* Bright ring */}
      <mesh ref={ringRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.15, 0]}>
        <ringGeometry args={[0.8, 1.0, 32]} />
        <meshBasicMaterial color="#f59e0b" transparent opacity={0.6} side={THREE.DoubleSide} />
      </mesh>
      {/* Vertical pin */}
      <mesh ref={beamRef} position={[0, 3, 0]}>
        <cylinderGeometry args={[0.015, 0.05, 6, 4]} />
        <meshBasicMaterial color="#f59e0b" transparent opacity={0.35} />
      </mesh>
      {/* Bright dot at base */}
      <mesh position={[0, 0.2, 0]}>
        <sphereGeometry args={[0.15, 8, 8]} />
        <meshBasicMaterial color="#f59e0b" />
      </mesh>
      {/* System name label floating above the pin */}
      {name && (
        <Html position={[0, 6.5, 0]} style={{ pointerEvents: 'none' }} distanceFactor={20}>
          <div style={{
            fontFamily: 'monospace',
            fontSize: 11,
            fontWeight: 'bold',
            color: '#f59e0b',
            textShadow: '0 0 8px #f59e0b, 0 0 20px rgba(0,0,0,0.95)',
            whiteSpace: 'nowrap',
            textAlign: 'center',
          }}>
            {name}
          </div>
        </Html>
      )}
    </group>
  )
}

// Smooth camera fly-to animation
function CameraFlyTo({ target }) {
  const { camera } = useThree()
  const targetRef = useRef(null)
  const lookAtRef = useRef(new THREE.Vector3())

  useEffect(() => {
    if (target) {
      targetRef.current = new THREE.Vector3(target[0], target[1], target[2])
      lookAtRef.current.set(target[0], 0, target[2])
    }
  }, [target])

  useFrame(() => {
    if (!targetRef.current) return
    // Fly camera toward a position offset above and in front of the target
    const dest = targetRef.current.clone()
    dest.y += 8
    dest.z += 12

    camera.position.lerp(dest, 0.03)
    const dist = camera.position.distanceTo(dest)
    if (dist < 0.5) {
      targetRef.current = null
    }
  })

  return null
}

// 3D route lines — smooth arcs between connected systems
function RouteLines({ connections }) {
  const lines = useMemo(() => {
    if (!connections || connections.length === 0) return []
    return connections.map((c) => {
      const sx = (c.source_nx - 0.5) * 70, sz = (c.source_nz - 0.5) * 70
      const dx = (c.dest_nx - 0.5) * 70, dz = (c.dest_nz - 0.5) * 70
      const dist = Math.sqrt((dx - sx) ** 2 + (dz - sz) ** 2)
      const arcHeight = 1.5 + Math.min(dist * 0.08, 4)
      // Smooth arc with 12 points
      const points = []
      for (let t = 0; t <= 1; t += 1 / 12) {
        const x = sx + (dx - sx) * t
        const z = sz + (dz - sz) * t
        const y = Math.sin(t * Math.PI) * arcHeight + 0.2
        points.push([x, y, z])
      }
      return { points, transits: c.transits }
    })
  }, [connections])

  if (lines.length === 0) return null

  return (
    <group>
      {lines.map((line, i) => (
        <Line
          key={i}
          points={line.points}
          color="#2dd4bf"
          lineWidth={Math.max(1.5, Math.min(4, line.transits * 1.5))}
          transparent
          opacity={Math.min(0.8, 0.4 + (line.transits / 5) * 0.3)}
        />
      ))}
    </group>
  )
}

// Territory markers — glowing discs + rings + labels on the galactic plane
function TerritoryMarkers({ territory }) {
  if (!territory || territory.length === 0) return null

  const TERR_COLORS = ['#3b82f6', '#ef4444', '#22c55e', '#a855f7', '#f59e0b', '#ec4899', '#06b6d4', '#84cc16']
  const entityColorMap = {}
  let colorIdx = 0

  return (
    <group>
      {territory.map((t) => {
        if (!entityColorMap[t.dominant_entity]) {
          entityColorMap[t.dominant_entity] = TERR_COLORS[colorIdx % TERR_COLORS.length]
          colorIdx++
        }
        const color = entityColorMap[t.dominant_entity]
        const x = (t.nx - 0.5) * 70
        const z = (t.nz - 0.5) * 70
        const radius = 1.0 + Math.min(t.total_kills, 15) * 0.15

        return (
          <group key={t.system_id} position={[x, 0, z]}>
            {/* Subtle border ring only — no fill disc */}
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
              <ringGeometry args={[radius, radius + 0.08, 24]} />
              <meshBasicMaterial color={color} transparent opacity={0.2} side={THREE.DoubleSide} />
            </mesh>
          </group>
        )
      })}
    </group>
  )
}

// Kill flash markers — pulsing beams at hotzone locations
function KillFlashes({ hotzones }) {
  const groupRefs = useRef([])

  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    groupRefs.current.forEach((group, i) => {
      if (!group) return
      const pulse = 1 + Math.sin(t * 2.5 + i * 1.2) * 0.2
      group.scale.y = pulse
    })
  })

  if (!hotzones || hotzones.length === 0) return null

  return (
    <group>
      {hotzones.slice(0, 20).map((hz, i) => {
        const x = (hz.nx - 0.5) * 70
        const z = (hz.nz - 0.5) * 70
        const dangerColor = hz.danger_level === 'extreme' ? '#ef4444'
          : hz.danger_level === 'high' ? '#f97316' : '#eab308'
        const height = 0.3 + Math.min(hz.kills, 20) * 0.08
        const intensity = Math.min(hz.kills, 20) / 20

        return (
          <group key={hz.system_id} ref={(el) => { groupRefs.current[i] = el }}>
            {/* Thin vertical pin */}
            <mesh position={[x, height / 2 + 0.1, z]}>
              <cylinderGeometry args={[0.02, 0.04, height, 4]} />
              <meshBasicMaterial color={dangerColor} transparent opacity={0.3 + intensity * 0.2} />
            </mesh>
          </group>
        )
      })}
    </group>
  )
}

// Radar sweep — rotating scan line on the galactic plane
function RadarSweep() {
  const meshRef = useRef()

  useFrame(({ clock }) => {
    if (meshRef.current) {
      meshRef.current.rotation.y = clock.elapsedTime * 0.3
    }
  })

  // Create a thin wedge shape
  const shape = useMemo(() => {
    const s = new THREE.Shape()
    const sweepAngle = Math.PI / 12 // 15 degree sweep
    const r = 40
    s.moveTo(0, 0)
    s.lineTo(Math.cos(-sweepAngle / 2) * r, Math.sin(-sweepAngle / 2) * r)
    s.absarc(0, 0, r, -sweepAngle / 2, sweepAngle / 2, false)
    s.lineTo(0, 0)
    return s
  }, [])

  return (
    <mesh ref={meshRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>
      <shapeGeometry args={[shape]} />
      <meshBasicMaterial color="#22c55e" transparent opacity={0.04} side={THREE.DoubleSide} />
    </mesh>
  )
}

// Animated particles flowing along route lines
function RouteParticles({ connections }) {
  const pointsRef = useRef()
  const particleData = useMemo(() => {
    if (!connections || connections.length === 0) return null
    const positions = []
    const meta = [] // store route index + t offset per particle
    const PARTICLES_PER_ROUTE = 4

    connections.forEach((c, routeIdx) => {
      const sx = (c.source_nx - 0.5) * 70, sz = (c.source_nz - 0.5) * 70
      const dx = (c.dest_nx - 0.5) * 70, dz = (c.dest_nz - 0.5) * 70
      for (let p = 0; p < PARTICLES_PER_ROUTE; p++) {
        positions.push(sx, 0.5, sz)
        meta.push({ routeIdx, sx, sz, dx, dz, offset: p / PARTICLES_PER_ROUTE })
      }
    })

    return {
      positions: new Float32Array(positions),
      meta,
      count: meta.length,
    }
  }, [connections])

  useFrame(({ clock }) => {
    if (!pointsRef.current || !particleData) return
    const posArr = pointsRef.current.geometry.attributes.position.array
    const t = clock.elapsedTime

    particleData.meta.forEach((m, i) => {
      const progress = ((t * 0.3 + m.offset) % 1)
      const x = m.sx + (m.dx - m.sx) * progress
      const z = m.sz + (m.dz - m.sz) * progress
      const dist = Math.sqrt((m.dx - m.sx) ** 2 + (m.dz - m.sz) ** 2)
      const arcH = 1.0 + Math.min(dist * 0.06, 3)
      const y = Math.sin(progress * Math.PI) * arcH + 0.3

      posArr[i * 3] = x
      posArr[i * 3 + 1] = y
      posArr[i * 3 + 2] = z
    })

    pointsRef.current.geometry.attributes.position.needsUpdate = true
  })

  if (!particleData) return null

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={particleData.count}
          array={particleData.positions}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial color="#2dd4bf" size={0.25} transparent opacity={0.8} sizeAttenuation depthWrite={false} />
    </points>
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

const DANGER_BADGE = {
  extreme: { color: '#ef4444', bg: '#ef444420', label: 'EXTREME' },
  high: { color: '#f97316', bg: '#f9731620', label: 'HIGH' },
  moderate: { color: '#eab308', bg: '#eab30820', label: 'MODERATE' },
  minimal: { color: '#22c55e', bg: '#22c55e20', label: 'LOW' },
}

function SystemIntelCard({ system, wtData, onClose, onViewAnomalies }) {
  const hotzones = wtData?.hotzones || []
  const killers = wtData?.top_killers || []
  const conflicts = wtData?.conflict_zones || []
  const territory = wtData?.territory || []
  const threats = wtData?.threat_systems || []

  // Find matching intel for this system
  const hotzone = hotzones.find(h => h.system_id === system.system_id)
  const threat = threats.find(t => t.system_id === system.system_id)
  const conflict = conflicts.find(c => c.system_id === system.system_id)
  const terr = territory.find(t => t.system_id === system.system_id)
  const nearbyKillers = killers.filter(k => k.system_id === system.system_id)
  const allKillers = killers

  const dangerLevel = hotzone?.danger_level || threat?.threat_level || 'minimal'
  const badge = DANGER_BADGE[dangerLevel] || DANGER_BADGE.minimal
  const severity = getMaxSeverity(system)

  return (
    <div className="absolute top-16 left-4 w-64 pointer-events-auto" style={{ maxWidth: 'calc(100vw - 300px)' }}>
      <div className="bg-[#0a0a0a]/95 border border-[#f59e0b]/40 rounded backdrop-blur-sm">
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-[#2a2a2a]">
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: SEVERITY_COLORS[severity] }} />
            <span className="text-[11px] font-bold text-white truncate">{system.name || system.system_id}</span>
          </div>
          <button onClick={onClose} className="text-[#6b7280] hover:text-white text-sm bg-transparent border-none cursor-pointer ml-2">&times;</button>
        </div>

        {/* Threat badge */}
        <div className="px-3 py-1.5 flex items-center gap-2 border-b border-[#1a1a1a]">
          <span className="text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded" style={{ color: badge.color, backgroundColor: badge.bg }}>
            {badge.label}
          </span>
          {threat && <span className="text-[9px] text-[#6b7280]">Score: {Math.round(threat.threat_score)}</span>}
          {conflict && <span className="text-[8px] text-pink-400 font-bold">CONTESTED</span>}
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-3 gap-px bg-[#1a1a1a] border-b border-[#1a1a1a]">
          <div className="bg-[#0a0a0a] px-2 py-1.5 text-center">
            <div className="text-[11px] font-bold text-[#f59e0b]">{system.count}</div>
            <div className="text-[7px] text-[#6b7280] uppercase">Anomalies</div>
          </div>
          <div className="bg-[#0a0a0a] px-2 py-1.5 text-center">
            <div className="text-[11px] font-bold text-red-400">{hotzone?.kills || 0}</div>
            <div className="text-[7px] text-[#6b7280] uppercase">Kills (7d)</div>
          </div>
          <div className="bg-[#0a0a0a] px-2 py-1.5 text-center">
            <div className="text-[11px] font-bold text-[#2dd4bf]">{hotzone?.unique_attackers || 0}</div>
            <div className="text-[7px] text-[#6b7280] uppercase">Attackers</div>
          </div>
        </div>

        {/* Severity breakdown */}
        {(system.critical > 0 || system.high > 0) && (
          <div className="px-3 py-1.5 flex gap-3 text-[9px] border-b border-[#1a1a1a]">
            {system.critical > 0 && <span style={{ color: SEVERITY_COLORS.critical }}>CRIT: {system.critical}</span>}
            {system.high > 0 && <span style={{ color: SEVERITY_COLORS.high }}>HIGH: {system.high}</span>}
            {system.medium > 0 && <span style={{ color: SEVERITY_COLORS.medium }}>MED: {system.medium}</span>}
            {system.low > 0 && <span className="text-[#6b7280]">LOW: {system.low}</span>}
          </div>
        )}

        {/* Territory control */}
        {terr && (
          <div className="px-3 py-1.5 border-b border-[#1a1a1a]">
            <div className="text-[8px] text-[#6b7280] uppercase tracking-wider mb-0.5">Dominant Force</div>
            <div className="text-[10px] text-[#e5e5e5] font-bold">{terr.dominant_name}</div>
            <div className="text-[8px] text-[#6b7280]">{terr.kill_count} kills · {Math.round(terr.dominance * 100)}% control</div>
          </div>
        )}

        {/* Nearby threats */}
        {nearbyKillers.length > 0 && (
          <div className="px-3 py-1.5 border-b border-[#1a1a1a]">
            <div className="text-[8px] text-[#6b7280] uppercase tracking-wider mb-1">Active Threats</div>
            {nearbyKillers.map(k => (
              <div key={k.entity_id} className="flex items-center gap-1.5 py-0.5">
                <span className="w-1 h-1 rounded-full bg-red-500" />
                <a
                  href={`https://watchtower-evefrontier.vercel.app/entity/${k.entity_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[9px] text-red-400 font-bold hover:underline no-underline"
                >
                  {k.display_name}
                </a>
                <span className="text-[8px] text-[#6b7280] ml-auto">{k.score} kills</span>
              </div>
            ))}
          </div>
        )}

        {/* All killers — show even if not "nearby" */}
        {nearbyKillers.length === 0 && allKillers.length > 0 && (
          <div className="px-3 py-1.5 border-b border-[#1a1a1a]">
            <div className="text-[8px] text-[#6b7280] uppercase tracking-wider mb-1">Top Threats (all systems)</div>
            {allKillers.slice(0, 3).map(k => (
              <div key={k.entity_id} className="flex items-center gap-1.5 py-0.5">
                <span className="w-1 h-1 rounded-full bg-red-500/50" />
                <a
                  href={`https://watchtower-evefrontier.vercel.app/entity/${k.entity_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[9px] text-red-400/70 hover:underline no-underline"
                >
                  {k.display_name}
                </a>
                <span className="text-[8px] text-[#6b7280] ml-auto">{k.system_name}</span>
              </div>
            ))}
          </div>
        )}

        {/* Actions */}
        <div className="flex border-t border-[#2a2a2a]">
          <button
            onClick={onViewAnomalies}
            className="flex-1 text-center px-2.5 py-1.5 text-[9px] font-bold text-[#f59e0b] hover:text-[#fbbf24] hover:bg-[#1a1a1a] bg-transparent border-none cursor-pointer uppercase tracking-wider transition-colors border-r border-[#2a2a2a]"
          >
            Anomalies &rarr;
          </button>
          {hotzone && (
            <a
              href={`https://watchtower-evefrontier.vercel.app/system/${system.system_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 text-center px-2.5 py-1.5 text-[9px] font-bold text-[#2dd4bf] hover:text-[#5eead4] hover:bg-[#1a1a1a] no-underline uppercase tracking-wider transition-colors"
            >
              WatchTower &rarr;
            </a>
          )}
        </div>
      </div>
    </div>
  )
}

function IntelPanel({ visibleSeverities, toggleSeverity, anomalySystems, onFlyTo }) {
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
    { key: 'layers', label: 'Layers', count: null },
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
                  <div key={k.entity_id} onClick={() => onFlyTo && onFlyTo(k.system_id)} className="flex items-center gap-2 px-2.5 py-1.5 border-b border-[#1a1a1a] last:border-0 cursor-pointer hover:bg-[#1a1a1a] transition-colors">
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
                  <div key={cz.system_id} onClick={() => onFlyTo && onFlyTo(cz.system_id)} className="flex items-center gap-2 px-2.5 py-1.5 border-b border-[#1a1a1a] last:border-0 cursor-pointer hover:bg-[#1a1a1a] transition-colors">
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
                  <div key={hz.system_id} onClick={() => onFlyTo && onFlyTo(hz.system_id)} className="flex items-center gap-2 px-2.5 py-1.5 border-b border-[#1a1a1a] last:border-0 cursor-pointer hover:bg-[#1a1a1a] transition-colors">
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
              {activeTab === 'layers' && visibleSeverities && (
                <div className="px-2.5 py-2 space-y-1">
                  <div className="text-[8px] text-[#6b7280] uppercase tracking-wider font-bold mb-1">Map Layers</div>
                  {Object.entries(SEVERITY_COLORS).map(([level, color]) => {
                    const active = visibleSeverities[level]
                    const count = (anomalySystems || []).filter((s) => getMaxSeverity(s) === level).length
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
                          {level} ({count})
                        </span>
                        <span className="text-[9px] ml-auto" style={{ color: active ? '#22c55e' : '#ef4444' }}>
                          {active ? 'ON' : 'OFF'}
                        </span>
                      </button>
                    )
                  })}
                </div>
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
  const [bgSystemsList, setBgSystemsList] = useState([])
  const [anomalySystems, setAnomalySystems] = useState([])
  const [hovered, setHovered] = useState(null)
  const [selectedSystem, setSelectedSystem] = useState(null)
  const [flyTarget, setFlyTarget] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [visibleSeverities, setVisibleSeverities] = useState({
    critical: true, high: true, medium: true, low: true,
  })

  const toggleSeverity = useCallback((level) => {
    setVisibleSeverities((prev) => ({ ...prev, [level]: !prev[level] }))
  }, [])

  const { data: mapData, loading: mapLoading } = useApi('/api/stats/map', { poll: 60000 })
  const { data: bgData, refetch: refetchBg } = useApi('/api/stats/map/systems', { poll: 0 })
  const { data: wtData } = useApi('/api/stats/map/watchtower', { poll: 60000 })

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
    const orderedSystems = []
    for (const s of allSystems) {
      if (s.nx == null || s.nz == null) continue
      const x = (s.nx - 0.5) * 70
      const z = (s.nz - 0.5) * 70
      const distFromCenter = Math.sqrt(x * x + z * z)
      const maxThickness = 3
      const thickness = maxThickness * Math.exp(-distFromCenter * distFromCenter / 800)
      const y = (Math.random() - 0.5) * 2 * thickness
      positions.push(x, y, z)
      orderedSystems.push(s)
    }
    setBgPositions(new Float32Array(positions))
    setBgSystemsList(orderedSystems)
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
    setSelectedSystem(prev => prev?.system_id === system.system_id ? null : system)
    if (system.nx != null && system.nz != null) {
      setFlyTarget([(system.nx - 0.5) * 70, 0, (system.nz - 0.5) * 70])
    }
  }, [])

  // Handle click on any background system dot
  const handleBgSystemClick = useCallback((sys) => {
    if (!sys) return
    setFlyTarget([(sys.nx - 0.5) * 70, 0, (sys.nz - 0.5) * 70])
    const anomaly = anomalySystems.find(a => a.system_id === sys.system_id)
    setSelectedSystem(anomaly || {
      system_id: sys.system_id,
      name: sys.name || sys.system_id,
      nx: sys.nx, nz: sys.nz,
      count: 0, critical: 0, high: 0, medium: 0, low: 0,
    })
  }, [anomalySystems])

  // Fly to a system by ID — used by Intel panel items
  const flyToSystem = useCallback((systemId) => {
    const allSystems = bgData?.all_systems || []
    const sys = allSystems.find(s => s.system_id === systemId)
    if (!sys || sys.nx == null) return
    setFlyTarget([(sys.nx - 0.5) * 70, 0, (sys.nz - 0.5) * 70])
    // Find matching anomaly system for the Intel Card, or create a minimal one
    const anomaly = anomalySystems.find(a => a.system_id === systemId)
    setSelectedSystem(anomaly || {
      system_id: systemId,
      name: sys.name || systemId,
      nx: sys.nx,
      nz: sys.nz,
      count: 0, critical: 0, high: 0, medium: 0, low: 0,
    })
  }, [bgData, anomalySystems])

  // Search systems by name
  const handleSearch = useCallback((query) => {
    setSearchQuery(query)
    if (!query || query.length < 2) {
      setSearchResults([])
      return
    }
    const allSystems = bgData?.all_systems || []
    const q = query.toLowerCase()
    const matches = allSystems
      .filter(s => s.name && s.name.toLowerCase().includes(q))
      .slice(0, 8)
    setSearchResults(matches)
  }, [bgData])

  const handleSearchSelect = useCallback((sys) => {
    setSearchQuery('')
    setSearchResults([])
    flyToSystem(sys.system_id)
  }, [flyToSystem])

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
          <ambientLight intensity={0.3} />
          <pointLight position={[0, 30, 0]} intensity={0.6} color="#6688ff" />
          <pointLight position={[0, -10, 0]} intensity={0.2} color="#223344" />

          <OrbitControls
            autoRotate
            autoRotateSpeed={0.15}
            enableDamping
            dampingFactor={0.05}
            minDistance={10}
            maxDistance={100}
            enablePan
            maxPolarAngle={Math.PI * 0.85}
            minPolarAngle={Math.PI * 0.15}
          />

          {/* Deep space background */}
          <Stars radius={150} depth={80} count={5000} factor={4} saturation={0.15} fade speed={0.3} />

          <CameraFlyTo target={flyTarget} />
          <SelectionBeacon position={flyTarget} name={selectedSystem?.name} />
          <RadarSweep />
          <SpaceDust />

          {/* Galaxy disc */}
          {bgPositions && <GalaxyField positions={bgPositions} systems={bgSystemsList} onSystemClick={handleBgSystemClick} />}

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

          {/* Heat map gradient */}
          <HeatMap hotzones={wtData?.hotzones} />

          {/* 3D route lines */}
          <RouteLines connections={wtData?.gate_connections} />

          {/* Animated route particles */}
          <RouteParticles connections={wtData?.gate_connections} />

          {/* Territory discs */}
          <TerritoryMarkers territory={wtData?.territory} />

          {/* Kill flash markers */}
          <KillFlashes hotzones={wtData?.hotzones} />

          {/* Bloom post-processing */}
          <EffectComposer>
            <Bloom
              luminanceThreshold={0.6}
              luminanceSmoothing={0.4}
              intensity={2.0}
              radius={0.9}
            />
          </EffectComposer>
        </Suspense>
      </Canvas>
      </div>

      {/* UI overlay layer — sits above Canvas with pointer-events passthrough */}
      <div className="absolute inset-0 pointer-events-none" style={{ zIndex: 50 }}>

      <div className="absolute top-3 left-4 pointer-events-auto">
        <div className="flex items-center gap-3">
          <div>
            <div className="text-[10px] font-bold text-[#f59e0b] uppercase tracking-wider">Galaxy Map</div>
            <div className="text-[9px] text-[#6b7280]">
              {bgPositions ? (bgPositions.length / 3).toLocaleString() : 0} systems · {totalAnomalies} anomalies
            </div>
          </div>
          <div className="relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              placeholder="Search system..."
              className="bg-[#0a0a0a]/90 border border-[#2a2a2a] rounded px-2 py-1 text-[10px] text-white w-36 focus:border-[#f59e0b] focus:outline-none placeholder-[#6b7280]"
            />
            {searchResults.length > 0 && (
              <div className="absolute top-full left-0 mt-1 w-48 bg-[#0a0a0a]/95 border border-[#2a2a2a] rounded max-h-[200px] overflow-y-auto z-50">
                {searchResults.map((sys) => (
                  <button
                    key={sys.system_id}
                    onClick={() => handleSearchSelect(sys)}
                    className="w-full text-left px-2 py-1.5 text-[10px] text-[#e5e5e5] hover:bg-[#1a1a1a] bg-transparent border-none cursor-pointer border-b border-[#1a1a1a] last:border-0 transition-colors"
                  >
                    {sys.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Severity legend — compact, bottom-left */}
      <div className="absolute bottom-3 left-4 bg-[#0a0a0a]/60 rounded px-2 py-1 flex gap-3 pointer-events-none">
        {Object.entries(SEVERITY_COLORS).map(([level, color]) => (
          <div key={level} className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color, opacity: visibleSeverities[level] ? 1 : 0.2 }} />
            <span className="text-[8px] uppercase" style={{ color, opacity: visibleSeverities[level] ? 0.8 : 0.2 }}>{level}</span>
          </div>
        ))}
      </div>

      <div className="absolute bottom-3 right-4 text-[9px] text-[#6b7280]">
        Drag to rotate · Scroll to zoom · Right-click to pan
      </div>

      <LiveFeed />
      <IntelPanel visibleSeverities={visibleSeverities} toggleSeverity={toggleSeverity} anomalySystems={anomalySystems} onFlyTo={flyToSystem} />

      {/* Hover tooltip */}
      {hovered && !selectedSystem && (
        <div className="absolute top-[17rem] right-4 bg-[#0a0a0a]/90 border border-[#2a2a2a] rounded px-3 py-2 text-xs space-y-0.5 pointer-events-auto">
          <div className="font-bold text-[#e5e5e5]">{hovered.name || hovered.system_id}</div>
          <div style={{ color: SEVERITY_COLORS[getMaxSeverity(hovered)] }}>
            {getMaxSeverity(hovered).toUpperCase()} — {hovered.count} anomalies
          </div>
          {hovered.critical > 0 && <div className="text-[#ef4444]">{hovered.critical} critical</div>}
          {hovered.high > 0 && <div className="text-[#f97316]">{hovered.high} high</div>}
          <div className="text-[9px] text-[#6b7280]">Click for intel</div>
        </div>
      )}

      {/* System Intel Card — fused WatchTower data */}
      {selectedSystem && (
        <SystemIntelCard
          system={selectedSystem}
          wtData={wtData}
          onClose={() => setSelectedSystem(null)}
          onViewAnomalies={() => navigate(`/anomalies?system_id=${selectedSystem.system_id}`)}
        />
      )}

      </div>{/* end overlay layer */}
    </div>
  )
}
