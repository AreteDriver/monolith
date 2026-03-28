/**
 * MapView3D — React Three Fiber galaxy map for Monolith.
 *
 * Shows 24K background systems as a dim point cloud with anomaly-affected
 * systems as glowing colored spheres. Size = anomaly count, color = max
 * severity. Auto-rotation, hover tooltip, click to navigate.
 * WatchTower hotzone overlay as secondary markers.
 */
import { useCallback, useEffect, useState, useRef, Suspense } from 'react'
import { useNavigate } from 'react-router-dom'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Points, PointMaterial, Html } from '@react-three/drei'
import * as THREE from 'three'
import { useApi } from '../hooks/useApi'
import { getDisplayName } from '../displayNames'

const SEVERITY_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#6b7280',
}

function getMaxSeverity(sys) {
  if (sys.critical > 0) return 'critical'
  if (sys.high > 0) return 'high'
  if (sys.medium > 0) return 'medium'
  return 'low'
}

function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

// Background star field from all 24K systems
function StarField({ positions }) {
  const ref = useRef()

  useFrame(() => {
    if (ref.current) ref.current.rotation.y += 0.00008
  })

  if (!positions || positions.length === 0) return null

  return (
    <Points ref={ref} positions={positions} stride={3}>
      <PointMaterial
        transparent
        color="#334"
        size={0.2}
        sizeAttenuation
        depthWrite={false}
        opacity={0.25}
      />
    </Points>
  )
}

// Anomaly marker sphere
function AnomalyMarker({ position, system, onHover, onClick }) {
  const glowRef = useRef()
  const severity = getMaxSeverity(system)
  const color = SEVERITY_COLORS[severity]
  const radius = Math.max(0.25, Math.min(1.0, Math.sqrt(system.count) * 0.3))
  const isHot = severity === 'critical' || severity === 'high'

  useFrame(({ clock }) => {
    if (glowRef.current && isHot) {
      const pulse = 1 + Math.sin(clock.elapsedTime * 2.5 + system.count) * 0.25
      glowRef.current.scale.setScalar(pulse)
    }
  })

  const name = system.name || system.system_id?.slice(0, 10)

  return (
    <group position={position}>
      {/* Outer glow */}
      <mesh ref={glowRef}>
        <sphereGeometry args={[radius * 2.5, 12, 12]} />
        <meshBasicMaterial color={color} transparent opacity={0.06} />
      </mesh>
      {/* Mid glow */}
      <mesh>
        <sphereGeometry args={[radius * 1.5, 12, 12]} />
        <meshBasicMaterial color={color} transparent opacity={0.12} />
      </mesh>
      {/* Core */}
      <mesh
        onPointerOver={(e) => { e.stopPropagation(); onHover(system) }}
        onPointerOut={() => onHover(null)}
        onClick={(e) => { e.stopPropagation(); onClick(system) }}
      >
        <sphereGeometry args={[radius, 12, 12]} />
        <meshBasicMaterial color={color} />
      </mesh>
      {/* Label for significant anomalies */}
      {system.count >= 3 && (
        <Html
          position={[radius + 0.4, 0.2, 0]}
          style={{ pointerEvents: 'none', whiteSpace: 'nowrap' }}
          distanceFactor={30}
        >
          <div style={{
            fontFamily: 'monospace',
            fontSize: 9,
            color: color,
            textShadow: '0 0 4px rgba(0,0,0,0.9)',
            opacity: 0.85,
          }}>
            {name}
            <span style={{ color: '#6b7280', marginLeft: 3 }}>{system.count}</span>
          </div>
        </Html>
      )}
    </group>
  )
}

// Auto-rotation
function AutoRotate() {
  const { camera } = useThree()
  const angleRef = useRef(0)

  useFrame(() => {
    angleRef.current += 0.0008
    const radius = 55
    camera.position.x = Math.cos(angleRef.current) * radius
    camera.position.z = Math.sin(angleRef.current) * radius
    camera.lookAt(0, 0, 0)
  })

  return null
}

function GridPlane() {
  return (
    <gridHelper
      args={[70, 20, '#1a1a2a', '#10101a']}
      position={[0, -12, 0]}
    />
  )
}

// Ambient dust particles floating in space
function SpaceDust() {
  const ref = useRef()
  const [positions] = useState(() => {
    const p = new Float32Array(600 * 3)
    for (let i = 0; i < 600; i++) {
      p[i * 3] = (Math.random() - 0.5) * 100
      p[i * 3 + 1] = (Math.random() - 0.5) * 40
      p[i * 3 + 2] = (Math.random() - 0.5) * 100
    }
    return p
  })

  useFrame(({ clock }) => {
    if (ref.current) {
      ref.current.rotation.y = clock.elapsedTime * 0.02
      ref.current.rotation.x = Math.sin(clock.elapsedTime * 0.01) * 0.05
    }
  })

  return (
    <Points ref={ref} positions={positions} stride={3}>
      <PointMaterial
        transparent
        color="#445"
        size={0.15}
        sizeAttenuation
        depthWrite={false}
        opacity={0.4}
      />
    </Points>
  )
}

// Nebula glow — colored fog spheres
function NebulaCloud({ position, color, size }) {
  return (
    <mesh position={position}>
      <sphereGeometry args={[size, 16, 16]} />
      <meshBasicMaterial color={color} transparent opacity={0.015} side={THREE.BackSide} />
    </mesh>
  )
}

export default function MapView3D() {
  const navigate = useNavigate()
  const [bgPositions, setBgPositions] = useState(null)
  const [anomalySystems, setAnomalySystems] = useState([])
  const [hovered, setHovered] = useState(null)

  const { data: mapData, loading: mapLoading } = useApi('/api/stats/map', { poll: 60000 })
  const { data: bgData } = useApi('/api/stats/map/systems', { poll: 0 })

  // Build background positions from all systems
  useEffect(() => {
    const allSystems = bgData?.all_systems || []
    if (allSystems.length === 0) return

    // Sample every 8th for performance (~3K points)
    const positions = []
    for (let i = 0; i < allSystems.length; i += 8) {
      const s = allSystems[i]
      positions.push(
        (s.nx - 0.5) * 70,
        (Math.random() - 0.5) * 6,
        ((s.nz || 0) - 0.5) * 70,
      )
    }
    setBgPositions(new Float32Array(positions))
  }, [bgData])

  // Build anomaly markers with positions
  useEffect(() => {
    const systems = mapData?.systems || []
    const allSystems = bgData?.all_systems || []
    if (systems.length === 0 || allSystems.length === 0) return

    const lookup = new Map()
    for (const s of allSystems) {
      lookup.set(s.system_id, { nx: s.nx, nz: s.nz || 0, name: s.name })
    }

    const markers = systems
      .map((sys) => {
        const coords = lookup.get(sys.system_id)
        if (!coords) return null
        return { ...sys, nx: coords.nx, nz: coords.nz, name: coords.name || sys.system_id }
      })
      .filter(Boolean)
      .sort((a, b) => a.count - b.count)

    setAnomalySystems(markers)
  }, [mapData, bgData])

  const handleClick = useCallback((system) => {
    navigate(`/anomalies?system_id=${system.system_id}`)
  }, [navigate])

  const totalAnomalies = anomalySystems.reduce((sum, s) => sum + s.count, 0)

  if (mapLoading && !bgPositions) {
    return (
      <div className="bg-[#08080e] flex items-center justify-center" style={{ height: '100%', minHeight: 500 }}>
        <div className="flex items-center gap-2 text-[#6b7280] text-xs">
          <span className="text-[#f59e0b] animate-pulse">///</span>
          Loading galaxy...
        </div>
      </div>
    )
  }

  return (
    <div className="bg-[#08080e] relative" style={{ height: '100%', minHeight: 500 }}>
      {/* Header overlay */}
      <div className="absolute top-3 left-4 z-10">
        <div className="text-[10px] font-bold text-[#f59e0b] uppercase tracking-wider">
          Anomaly Map
        </div>
        <div className="text-[9px] text-[#6b7280]">
          {anomalySystems.length} systems · {totalAnomalies} anomalies
        </div>
      </div>

      {/* Legend */}
      <div className="absolute bottom-3 right-4 z-10 flex gap-3">
        {Object.entries(SEVERITY_COLORS).map(([level, color]) => (
          <span key={level} className="flex items-center gap-1 text-[8px] text-[#6b7280]">
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
            {level}
          </span>
        ))}
      </div>

      {/* Hover tooltip */}
      {hovered && (
        <div className="absolute top-3 right-4 z-10 bg-[#0a0a0a] border border-[#2a2a2a] rounded px-3 py-2 text-xs space-y-0.5">
          <div className="font-bold text-[#e5e5e5]">{hovered.name || hovered.system_id}</div>
          <div style={{ color: SEVERITY_COLORS[getMaxSeverity(hovered)] }}>
            {getMaxSeverity(hovered).toUpperCase()} — {hovered.count} anomalies
          </div>
          {hovered.critical > 0 && <div className="text-[#ef4444]">{hovered.critical} critical</div>}
          {hovered.high > 0 && <div className="text-[#f97316]">{hovered.high} high</div>}
          <div className="text-[9px] text-[#6b7280]">Click for anomaly feed</div>
        </div>
      )}

      <Canvas
        camera={{ position: [55, 18, 0], fov: 45, near: 0.1, far: 200 }}
        style={{ background: '#08080e' }}
      >
        <Suspense fallback={null}>
          <ambientLight intensity={0.3} />
          <AutoRotate />
          <GridPlane />
          <SpaceDust />

          {/* Nebula fog */}
          <NebulaCloud position={[-15, 5, -20]} color="#ef4444" size={18} />
          <NebulaCloud position={[20, -3, 15]} color="#3b82f6" size={22} />
          <NebulaCloud position={[5, 8, -25]} color="#a855f7" size={15} />
          <NebulaCloud position={[-25, -5, 10]} color="#10b981" size={16} />

          {bgPositions && <StarField positions={bgPositions} />}

          {anomalySystems.map((sys) => (
            <AnomalyMarker
              key={sys.system_id}
              position={[
                (sys.nx - 0.5) * 70,
                0,
                (sys.nz - 0.5) * 70,
              ]}
              system={sys}
              onHover={setHovered}
              onClick={handleClick}
            />
          ))}
        </Suspense>
      </Canvas>
    </div>
  )
}
