import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import PinButton from '../components/PinButton'
import { useApi } from '../hooks/useApi'
import { getTypeName } from '../displayNames'

const SEVERITY_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#6b7280',
}

const DANGER_COLORS = {
  extreme: '#ef4444',
  high: '#f97316',
  moderate: '#eab308',
  low: '#6b7280',
  minimal: '#334155',
}

const THREAT_COLORS = {
  extreme: '#ef4444',
  high: '#f97316',
  moderate: '#eab308',
  low: '#22c55e',
  minimal: '#334155',
}

const TREND_ARROWS = {
  surging: '\u25b2\u25b2',
  rising: '\u25b2',
  stable: '\u2500',
  declining: '\u25bc',
  collapsing: '\u25bc\u25bc',
  new: '\u2726',
  none: '',
}

const ASSEMBLY_COLORS = {
  online: '#22c55e',
  anchored: '#6b7280',
  offline: '#ef4444',
  unanchored: '#334155',
  unknown: '#334155',
}

const GATE_COLOR = '#2dd4bf'
const KILLER_COLOR = '#ef4444'
const CONFLICT_COLOR = '#f472b6'
const TERRITORY_COLORS = [
  '#3b82f6', '#ef4444', '#22c55e', '#a855f7', '#f59e0b',
  '#ec4899', '#06b6d4', '#84cc16',
]

const TYPE_COLORS = {
  // Continuity
  ORPHAN_OBJECT: '#6b7280',
  RESURRECTION: '#ef4444',
  STATE_GAP: '#eab308',
  STUCK_OBJECT: '#6b7280',
  // Economic
  SUPPLY_DISCREPANCY: '#3b82f6',
  UNEXPLAINED_DESTRUCTION: '#3b82f6',
  DUPLICATE_MINT: '#ef4444',
  NEGATIVE_BALANCE: '#ef4444',
  // Assembly
  CONTRACT_STATE_MISMATCH: '#10b981',
  FREE_GATE_JUMP: '#ec4899',
  FAILED_GATE_TRANSPORT: '#ec4899',
  PHANTOM_ITEM_CHANGE: '#f97316',
  UNEXPLAINED_OWNERSHIP_CHANGE: '#a855f7',
  // Sequence
  DUPLICATE_TRANSACTION: '#a855f7',
  BLOCK_PROCESSING_GAP: '#6b7280',
  // POD
  CHAIN_STATE_MISMATCH: '#ef4444',
  // Killmail
  DUPLICATE_KILLMAIL: '#ec4899',
  THIRD_PARTY_KILL_REPORT: '#ec4899',
  // Behavioral
  COORDINATED_BUYING: '#f97316',
  STATE_ROLLBACK: '#ef4444',
  UNAUTHORIZED_STATE_MODIFICATION: '#a855f7',
  ASSET_CONCENTRATION: '#eab308',
  CONFIG_VERSION_CHANGE: '#ef4444',
  INVENTORY_CONSERVATION_VIOLATION: '#ef4444',
  BOT_PATTERN: '#eab308',
  RAPID_TRIBE_CHANGE: '#eab308',
  ORPHANED_KILLMAIL: '#f97316',
  GHOST_ENGAGEMENT: '#ef4444',
  DEAD_ASSEMBLY: '#6b7280',
  VELOCITY_SPIKE: '#f97316',
  VELOCITY_DROP: '#3b82f6',
  OWNERCAP_TRANSFER: '#a855f7',
  OWNERCAP_DELEGATION: '#a855f7',
}

function getTypeColor(type) {
  return TYPE_COLORS[type] || '#6b7280'
}

function getMaxSeverity(sys) {
  if (sys.critical > 0) return 'critical'
  if (sys.high > 0) return 'high'
  if (sys.medium > 0) return 'medium'
  return 'low'
}

// --- PRE-COMPUTED STARFIELD (generated once, rendered every frame) ---
const STAR_COUNT = 1200
const STARS = Array.from({ length: STAR_COUNT }, () => ({
  x: Math.random(),
  y: Math.random(),
  r: Math.random() * 1.8 + 0.4,
  alpha: Math.random() * 0.6 + 0.15,
  twinkleSpeed: Math.random() * 0.003 + 0.001,
  twinkleOffset: Math.random() * Math.PI * 2,
}))

// --- NEBULA CLOUD DEFINITIONS (subtle colored fog patches) ---
const NEBULAE = [
  { x: 0.15, y: 0.25, r: 0.22, color: [239, 68, 68], alpha: 0.06 },     // red
  { x: 0.75, y: 0.15, r: 0.28, color: [59, 130, 246], alpha: 0.05 },    // blue
  { x: 0.5, y: 0.7, r: 0.25, color: [168, 85, 247], alpha: 0.05 },      // purple
  { x: 0.85, y: 0.65, r: 0.2, color: [245, 158, 11], alpha: 0.045 },    // amber
  { x: 0.3, y: 0.8, r: 0.2, color: [16, 185, 129], alpha: 0.04 },       // emerald
  { x: 0.6, y: 0.35, r: 0.16, color: [236, 72, 153], alpha: 0.04 },     // pink
]

export function AnomalyMap({ onSystemSelect, height } = {}) {
  const canvasRef = useRef(null)
  const containerRef = useRef(null)
  const [tooltip, setTooltip] = useState(null)
  const [selectedSystem, setSelectedSystem] = useState(null)
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 })
  const dragRef = useRef({ dragging: false, startX: 0, startY: 0, startTx: 0, startTy: 0 })
  const touchRef = useRef({ active: false, lastDist: 0, lastX: 0, lastY: 0 })
  const transformRef = useRef(transform)
  const systemsRef = useRef([])
  const eventsRef = useRef([])
  const bgSystemsRef = useRef([])
  const animRef = useRef(null)
  const drawRef = useRef(null)
  const wtHotzonesRef = useRef([])
  const wtThreatRef = useRef([])
  const wtAssembliesRef = useRef([])
  const wtGatesRef = useRef([])
  const wtKillersRef = useRef([])
  const wtTerritoryRef = useRef([])
  const wtConflictsRef = useRef([])
  const nebulaCanvasRef = useRef(null) // offscreen canvas for nebula (rendered once)
  const [layers, setLayers] = useState({
    background: true, anomalies: true,
    hotzones: true, threat: true, assemblies: false,
    gates: true, killers: true, territory: false, conflicts: true,
  })
  const layersRef = useRef(layers)

  const { data, loading } = useApi('/api/stats/map', { poll: 60000 })
  // Background systems are static — fetch once, cache in browser
  const { data: bgData } = useApi('/api/stats/map/systems', { poll: 0 })
  // WatchTower intelligence overlay — polls every 60s, serves stale on failure
  const { data: wtData } = useApi('/api/stats/map/watchtower', { poll: 60000 })

  // Compute normalized positions once when data arrives
  useEffect(() => {
    const bgSystems = bgData?.all_systems || []
    const systems = data?.systems || []
    const events = data?.recent_events || []

    if (!bgSystems.length && !systems.length) {
      systemsRef.current = []
      eventsRef.current = []
      bgSystemsRef.current = []
      return
    }

    // Server sends pre-normalized nx/nz (0..1) to avoid JS float64 precision
    // loss on 10^19-range coordinates that exceed Number.MAX_SAFE_INTEGER.
    bgSystemsRef.current = bgSystems
    systemsRef.current = systems
    eventsRef.current = events
  }, [data, bgData])

  // Sync WatchTower overlay data into refs
  useEffect(() => {
    wtHotzonesRef.current = wtData?.hotzones || []
    wtThreatRef.current = wtData?.threat_systems || []
    wtAssembliesRef.current = wtData?.assemblies || []
    wtGatesRef.current = wtData?.gate_connections || []
    wtKillersRef.current = wtData?.top_killers || []
    wtTerritoryRef.current = wtData?.territory || []
    wtConflictsRef.current = wtData?.conflict_zones || []
  }, [wtData])

  // Keep refs synced with state
  useEffect(() => { transformRef.current = transform }, [transform])
  useEffect(() => { layersRef.current = layers }, [layers])

  const draw = useCallback((timestamp) => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) {
      // Canvas not mounted yet — keep polling until it is
      animRef.current = requestAnimationFrame(drawRef.current)
      return
    }

    // Read from refs to avoid re-creating draw on every state change
    const transform = transformRef.current
    const layers = layersRef.current

    const rect = container.getBoundingClientRect()
    const dpr = window.devicePixelRatio || 1
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    canvas.style.width = `${rect.width}px`
    canvas.style.height = `${rect.height}px`

    const ctx = canvas.getContext('2d')
    ctx.scale(dpr, dpr)
    const w = rect.width
    const h = rect.height

    // Background
    ctx.fillStyle = '#050508'
    ctx.fillRect(0, 0, w, h)

    // --- NEBULA CLOUDS (offscreen canvas, rendered once per size) ---
    const nc = nebulaCanvasRef.current
    if (!nc || nc.width !== Math.floor(w) || nc.height !== Math.floor(h)) {
      const offscreen = document.createElement('canvas')
      offscreen.width = Math.floor(w)
      offscreen.height = Math.floor(h)
      const nctx = offscreen.getContext('2d')
      nctx.globalCompositeOperation = 'lighter'
      for (const neb of NEBULAE) {
        const nx = neb.x * w
        const ny = neb.y * h
        const nr = neb.r * Math.max(w, h)
        const grad = nctx.createRadialGradient(nx, ny, 0, nx, ny, nr)
        grad.addColorStop(0, `rgba(${neb.color[0]},${neb.color[1]},${neb.color[2]},${neb.alpha})`)
        grad.addColorStop(0.4, `rgba(${neb.color[0]},${neb.color[1]},${neb.color[2]},${neb.alpha * 0.5})`)
        grad.addColorStop(1, `rgba(${neb.color[0]},${neb.color[1]},${neb.color[2]},0)`)
        nctx.beginPath()
        nctx.arc(nx, ny, nr, 0, Math.PI * 2)
        nctx.fillStyle = grad
        nctx.fill()
      }
      nebulaCanvasRef.current = offscreen
    }
    ctx.drawImage(nebulaCanvasRef.current, 0, 0)

    // --- STARFIELD (twinkle animation) ---
    const ts = timestamp || 0
    for (const star of STARS) {
      const twinkle = Math.sin(ts * star.twinkleSpeed + star.twinkleOffset)
      const alpha = star.alpha + twinkle * 0.15
      if (alpha <= 0.02) continue
      ctx.beginPath()
      ctx.arc(star.x * w, star.y * h, star.r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(200,210,230,${Math.min(0.7, alpha)})`
      ctx.fill()
    }

    // Grid (fade with zoom — visible at low zoom, disappears at high)
    const gridAlpha = Math.max(0.03, 0.15 - (transform.scale - 1) * 0.03)
    ctx.strokeStyle = `rgba(34,34,34,${gridAlpha})`
    ctx.lineWidth = 0.5
    const gridSize = 60 * transform.scale
    const offsetX = transform.x % gridSize
    const offsetY = transform.y % gridSize
    for (let x = offsetX; x < w; x += gridSize) {
      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x, h)
      ctx.stroke()
    }
    for (let y = offsetY; y < h; y += gridSize) {
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(w, y)
      ctx.stroke()
    }

    // Scanline sweep effect (dual sweep for cinematic feel)
    const scanY = (ts * 0.03) % h
    const scanGrad = ctx.createLinearGradient(0, scanY - 40, 0, scanY + 40)
    scanGrad.addColorStop(0, 'rgba(245,158,11,0)')
    scanGrad.addColorStop(0.5, 'rgba(245,158,11,0.06)')
    scanGrad.addColorStop(1, 'rgba(245,158,11,0)')
    ctx.fillStyle = scanGrad
    ctx.fillRect(0, scanY - 40, w, 80)
    // Secondary slower sweep (blue tint)
    const scanY2 = (ts * 0.015 + h * 0.6) % h
    const scanGrad2 = ctx.createLinearGradient(0, scanY2 - 50, 0, scanY2 + 50)
    scanGrad2.addColorStop(0, 'rgba(59,130,246,0)')
    scanGrad2.addColorStop(0.5, 'rgba(59,130,246,0.015)')
    scanGrad2.addColorStop(1, 'rgba(59,130,246,0)')
    ctx.fillStyle = scanGrad2
    ctx.fillRect(0, scanY2 - 50, w, 100)

    const systems = systemsRef.current
    const events = eventsRef.current
    const bgSystems = bgSystemsRef.current

    if (!bgSystems.length && !systems.length) {
      ctx.fillStyle = '#6b7280'
      ctx.font = '14px -apple-system, sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('No map data available', w / 2, h / 2)
      return
    }

    const pad = 60
    const drawW = w - pad * 2
    const drawH = h - pad * 2

    // --- BACKGROUND SYSTEMS (dim dots with subtle twinkle) ---
    if (layers.background && bgSystems.length) {
      // Fade background as zoom increases: full opacity at 1x, nearly invisible at 4x+
      const bgAlpha = Math.max(0.08, 1 - (transform.scale - 1) * 0.3)
      const bgRadius = Math.min(2, Math.max(1, 1.5 * transform.scale))  // cap at 2px
      for (let i = 0; i < bgSystems.length; i++) {
        const sys = bgSystems[i]
        const sx = pad + sys.nx * drawW
        const sy = pad + sys.nz * drawH
        const px = sx * transform.scale + transform.x
        const py = sy * transform.scale + transform.y

        if (px < -5 || px > w + 5 || py < -5 || py > h + 5) continue

        // Subtle twinkle — use index as seed for stable per-star phase
        const twinkle = Math.sin(ts * 0.0008 + i * 1.7) * 0.3 + 0.7  // 0.4 - 1.0
        const a = bgAlpha * twinkle
        // Slight color variation: most are slate, some are warm
        const warm = (i % 17 === 0) ? 1 : 0
        ctx.fillStyle = warm
          ? `rgba(120,100,80,${a})`
          : `rgba(51,65,85,${a})`

        ctx.beginPath()
        ctx.arc(px, py, bgRadius, 0, Math.PI * 2)
        ctx.fill()
      }

      // Labels at higher zoom (also faded)
      if (transform.scale > 2.5 && bgAlpha > 0.15) {
        ctx.fillStyle = `rgba(51,65,85,${bgAlpha * 0.8})`
        ctx.font = `${Math.min(12, Math.max(8, 9 * transform.scale))}px -apple-system, sans-serif`
        ctx.textAlign = 'center'
        for (const sys of bgSystems) {
          const sx = pad + sys.nx * drawW
          const sy = pad + sys.nz * drawH
          const px = sx * transform.scale + transform.x
          const py = sy * transform.scale + transform.y
          if (px < -5 || px > w + 5 || py < -5 || py > h + 5) continue
          if (sys.name) ctx.fillText(sys.name, px, py - 5)
        }
      }
    }
    const maxCount = systems.length ? Math.max(...systems.map(s => s.count)) : 1
    const now = Date.now() / 1000

    // --- REPULSION: spread overlapping anomaly markers ---
    // Compute screen positions once, then push apart if too close
    const markerPos = systems.map(sys => {
      const sx = pad + sys.nx * drawW
      const sy = pad + sys.nz * drawH
      return {
        sys,
        px: sx * transform.scale + transform.x,
        py: sy * transform.scale + transform.y,
      }
    })
    const minDist = Math.max(40, 30 * transform.scale)
    // Run a few iterations of simple repulsion
    for (let iter = 0; iter < 8; iter++) {
      for (let i = 0; i < markerPos.length; i++) {
        for (let j = i + 1; j < markerPos.length; j++) {
          const dx = markerPos[j].px - markerPos[i].px
          const dy = markerPos[j].py - markerPos[i].py
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          if (dist < minDist) {
            const push = (minDist - dist) / 2
            const nx = dx / dist
            const ny = dy / dist
            markerPos[i].px -= nx * push
            markerPos[i].py -= ny * push
            markerPos[j].px += nx * push
            markerPos[j].py += ny * push
          }
        }
      }
    }

    // --- PROXIMITY LINKS (MST connecting anomaly systems) ---
    if (layers.anomalies && markerPos.length > 1) {
      // Prim's MST: connect all anomaly systems with minimum total distance
      const connected = new Set([0])
      const edges = []
      while (connected.size < markerPos.length) {
        let bestDist = Infinity
        let bestFrom = -1
        let bestTo = -1
        for (const i of connected) {
          for (let j = 0; j < markerPos.length; j++) {
            if (connected.has(j)) continue
            const dx = markerPos[i].px - markerPos[j].px
            const dy = markerPos[i].py - markerPos[j].py
            const dist = Math.sqrt(dx * dx + dy * dy)
            if (dist < bestDist) {
              bestDist = dist
              bestFrom = i
              bestTo = j
            }
          }
        }
        if (bestTo === -1) break
        connected.add(bestTo)
        edges.push([bestFrom, bestTo])
      }

      // Draw edges as dashed lines
      ctx.save()
      ctx.setLineDash([4, 6])
      ctx.lineWidth = 1
      for (const [i, j] of edges) {
        const a = markerPos[i]
        const b = markerPos[j]
        const severity = getMaxSeverity(a.sys)
        ctx.strokeStyle = SEVERITY_COLORS[severity] + '40'
        ctx.beginPath()
        ctx.moveTo(a.px, a.py)
        ctx.lineTo(b.px, b.py)
        ctx.stroke()
      }
      ctx.restore()
    }

    // --- HEATMAP LAYER ---
    if (layers.anomalies) {
      // Use globalCompositeOperation for additive blending
      ctx.save()
      ctx.globalCompositeOperation = 'lighter'

      for (const mp of markerPos) {
        const { sys, px, py } = mp

        if (px < -120 || px > w + 120 || py < -120 || py > h + 120) continue

        const intensity = sys.count / maxCount
        const baseRadius = 30 + intensity * 70
        const radius = baseRadius * transform.scale

        const severity = getMaxSeverity(sys)
        const color = SEVERITY_COLORS[severity]

        // Parse hex color for rgba
        const r = parseInt(color.slice(1, 3), 16)
        const g = parseInt(color.slice(3, 5), 16)
        const b = parseInt(color.slice(5, 7), 16)

        const grad = ctx.createRadialGradient(px, py, 0, px, py, radius)
        const alpha = 0.08 + intensity * 0.18
        grad.addColorStop(0, `rgba(${r},${g},${b},${alpha})`)
        grad.addColorStop(0.4, `rgba(${r},${g},${b},${alpha * 0.5})`)
        grad.addColorStop(1, `rgba(${r},${g},${b},0)`)

        ctx.beginPath()
        ctx.arc(px, py, radius, 0, Math.PI * 2)
        ctx.fillStyle = grad
        ctx.fill()
      }

      ctx.restore()
    }

    // --- WATCHTOWER: TERRITORY SHADING (dominant actor per system) ---
    if (layers.territory) {
      const terr = wtTerritoryRef.current
      if (terr.length) {
        ctx.save()
        ctx.globalCompositeOperation = 'lighter'
        // Assign stable colors by hashing entity ID
        const entityColorMap = {}
        let colorIdx = 0
        for (const t of terr) {
          if (!entityColorMap[t.dominant_entity]) {
            entityColorMap[t.dominant_entity] = TERRITORY_COLORS[colorIdx % TERRITORY_COLORS.length]
            colorIdx++
          }
          const sx = pad + t.nx * drawW
          const sy = pad + t.nz * drawH
          const px = sx * transform.scale + transform.x
          const py = sy * transform.scale + transform.y
          if (px < -100 || px > w + 100 || py < -100 || py > h + 100) continue

          const color = entityColorMap[t.dominant_entity]
          const r = parseInt(color.slice(1, 3), 16)
          const g = parseInt(color.slice(3, 5), 16)
          const b = parseInt(color.slice(5, 7), 16)
          const radius = (25 + Math.min(t.total_kills, 20) * 4) * transform.scale
          const alpha = 0.04 + t.dominance * 0.06

          const grad = ctx.createRadialGradient(px, py, 0, px, py, radius)
          grad.addColorStop(0, `rgba(${r},${g},${b},${alpha})`)
          grad.addColorStop(0.5, `rgba(${r},${g},${b},${alpha * 0.4})`)
          grad.addColorStop(1, `rgba(${r},${g},${b},0)`)
          ctx.fillStyle = grad
          ctx.beginPath()
          ctx.arc(px, py, radius, 0, Math.PI * 2)
          ctx.fill()
        }
        ctx.restore()
      }
    }

    // --- WATCHTOWER: HOTZONE RINGS (kill density zones) ---
    if (layers.hotzones) {
      const hotzones = wtHotzonesRef.current
      if (hotzones.length) {
        ctx.save()
        ctx.globalCompositeOperation = 'lighter'
        const maxKills = Math.max(...hotzones.map(h => h.kills), 1)
        for (const hz of hotzones) {
          const sx = pad + hz.nx * drawW
          const sy = pad + hz.nz * drawH
          const px = sx * transform.scale + transform.x
          const py = sy * transform.scale + transform.y
          if (px < -150 || px > w + 150 || py < -150 || py > h + 150) continue

          const color = DANGER_COLORS[hz.danger_level] || DANGER_COLORS.minimal
          const r = parseInt(color.slice(1, 3), 16)
          const g = parseInt(color.slice(3, 5), 16)
          const b = parseInt(color.slice(5, 7), 16)
          const intensity = hz.kills / maxKills
          const radius = (20 + intensity * 60) * transform.scale
          const alpha = 0.06 + intensity * 0.12

          // Concentric ring
          ctx.beginPath()
          ctx.arc(px, py, radius, 0, Math.PI * 2)
          ctx.strokeStyle = `rgba(${r},${g},${b},${alpha + 0.15})`
          ctx.lineWidth = 1.5
          ctx.stroke()

          // Fill glow
          const grad = ctx.createRadialGradient(px, py, 0, px, py, radius)
          grad.addColorStop(0, `rgba(${r},${g},${b},${alpha})`)
          grad.addColorStop(0.6, `rgba(${r},${g},${b},${alpha * 0.4})`)
          grad.addColorStop(1, `rgba(${r},${g},${b},0)`)
          ctx.fillStyle = grad
          ctx.fill()
        }
        ctx.restore()
      }
    }

    // --- WATCHTOWER: GATE CONNECTIONS (transit route lines) ---
    if (layers.gates) {
      const gates = wtGatesRef.current
      if (gates.length) {
        const maxTransits = Math.max(...gates.map(g => g.transits), 1)
        for (const g of gates) {
          const sx1 = (pad + g.source_nx * drawW) * transform.scale + transform.x
          const sy1 = (pad + g.source_nz * drawH) * transform.scale + transform.y
          const sx2 = (pad + g.dest_nx * drawW) * transform.scale + transform.x
          const sy2 = (pad + g.dest_nz * drawH) * transform.scale + transform.y

          // Cull if both endpoints off screen
          if ((sx1 < -50 && sx2 < -50) || (sx1 > w + 50 && sx2 > w + 50)) continue
          if ((sy1 < -50 && sy2 < -50) || (sy1 > h + 50 && sy2 > h + 50)) continue

          const intensity = g.transits / maxTransits
          const alpha = 0.15 + intensity * 0.45
          const lineW = Math.max(0.5, Math.min(3, Math.log2(g.transits + 1) * 0.8))

          ctx.beginPath()
          ctx.moveTo(sx1, sy1)
          ctx.lineTo(sx2, sy2)
          ctx.strokeStyle = `rgba(45,212,191,${alpha})`  // teal
          ctx.lineWidth = lineW
          ctx.setLineDash([6, 4])
          ctx.stroke()
          ctx.setLineDash([])

          // Label at midpoint at higher zoom
          if (transform.scale > 2.0 && g.transits >= 3) {
            const mx = (sx1 + sx2) / 2
            const my = (sy1 + sy2) / 2
            ctx.fillStyle = `rgba(45,212,191,${alpha})`
            ctx.font = `${Math.min(9, 8 * transform.scale)}px -apple-system, sans-serif`
            ctx.textAlign = 'center'
            ctx.fillText(`${g.transits}`, mx, my - 4)
          }
        }
      }
    }

    // --- WATCHTOWER: THREAT FORECAST (score indicators — zoom-gated) ---
    if (layers.threat && transform.scale >= 1.5) {
      const threats = wtThreatRef.current
      if (threats.length) {
        for (const ts of threats) {
          if (ts.threat_score < 10) continue // skip minimal-noise systems
          const sx = pad + ts.nx * drawW
          const sy = pad + ts.nz * drawH
          const px = sx * transform.scale + transform.x
          const py = sy * transform.scale + transform.y
          if (px < -20 || px > w + 20 || py < -20 || py > h + 20) continue

          const color = THREAT_COLORS[ts.threat_level] || THREAT_COLORS.minimal
          const arrow = TREND_ARROWS[ts.kill_trend] || ''
          const size = Math.min(12, Math.max(8, 9 * transform.scale))
          const score = Math.round(ts.threat_score)
          const label = arrow ? `${score} ${arrow}` : `${score}`

          // Measure text for background pill
          ctx.font = `bold ${size}px -apple-system, sans-serif`
          ctx.textAlign = 'left'
          const textW = ctx.measureText(label).width
          const pillX = px + 8
          const pillY = py - 4 - size + 1
          const pillH = size + 4
          const pillW = textW + 8
          const pillR = 3

          // Dark background pill
          ctx.fillStyle = 'rgba(10,10,10,0.85)'
          ctx.beginPath()
          ctx.roundRect(pillX - 4, pillY, pillW, pillH, pillR)
          ctx.fill()

          // Score + trend as single label
          ctx.fillStyle = color
          ctx.fillText(label, pillX, py - 4)
        }
      }
    }

    // --- SYSTEM MARKERS (using repulsed positions) ---
    if (layers.anomalies) {
      for (const mp of markerPos) {
        const { sys, px, py } = mp

        if (px < -20 || px > w + 20 || py < -20 || py > h + 20) continue

        const severity = getMaxSeverity(sys)
        const color = SEVERITY_COLORS[severity]
        const baseRadius = Math.max(6, 4 + (sys.count / maxCount) * 16)
        const radius = baseRadius * Math.max(1, transform.scale * 0.8)

        // Glow — strong and visible
        ctx.beginPath()
        ctx.arc(px, py, radius * 3, 0, Math.PI * 2)
        const glow = ctx.createRadialGradient(px, py, 0, px, py, radius * 3)
        glow.addColorStop(0, color + '60')
        glow.addColorStop(0.3, color + '30')
        glow.addColorStop(1, color + '00')
        ctx.fillStyle = glow
        ctx.fill()

        // Dot — bright core
        ctx.beginPath()
        ctx.arc(px, py, radius, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.fill()
        // White center pip for visibility
        ctx.beginPath()
        ctx.arc(px, py, Math.max(2, radius * 0.3), 0, Math.PI * 2)
        ctx.fillStyle = '#ffffff'
        ctx.fill()

        // Crosshair reticle for critical systems
        if (sys.critical > 0) {
          const reticleR = radius * 2
          ctx.strokeStyle = color + '60'
          ctx.lineWidth = 0.5
          ctx.beginPath()
          ctx.moveTo(px - reticleR, py)
          ctx.lineTo(px - radius - 2, py)
          ctx.moveTo(px + radius + 2, py)
          ctx.lineTo(px + reticleR, py)
          ctx.moveTo(px, py - reticleR)
          ctx.lineTo(px, py - radius - 2)
          ctx.moveTo(px, py + radius + 2)
          ctx.lineTo(px, py + reticleR)
          ctx.stroke()
          // Corner brackets
          ctx.beginPath()
          ctx.moveTo(px - reticleR, py - reticleR)
          ctx.lineTo(px - reticleR + 4, py - reticleR)
          ctx.moveTo(px - reticleR, py - reticleR)
          ctx.lineTo(px - reticleR, py - reticleR + 4)
          ctx.moveTo(px + reticleR, py - reticleR)
          ctx.lineTo(px + reticleR - 4, py - reticleR)
          ctx.moveTo(px + reticleR, py - reticleR)
          ctx.lineTo(px + reticleR, py - reticleR + 4)
          ctx.moveTo(px - reticleR, py + reticleR)
          ctx.lineTo(px - reticleR + 4, py + reticleR)
          ctx.moveTo(px - reticleR, py + reticleR)
          ctx.lineTo(px - reticleR, py + reticleR - 4)
          ctx.moveTo(px + reticleR, py + reticleR)
          ctx.lineTo(px + reticleR - 4, py + reticleR)
          ctx.moveTo(px + reticleR, py + reticleR)
          ctx.lineTo(px + reticleR, py + reticleR - 4)
          ctx.stroke()
        }

        // Label — always show for anomaly systems
        if (sys.name) {
          ctx.fillStyle = '#ffffff'
          ctx.font = `bold ${Math.min(14, Math.max(10, 11 * transform.scale))}px -apple-system, sans-serif`
          ctx.textAlign = 'center'
          ctx.fillText(sys.name, px, py - radius - 4)
        }
      }
    }

    // --- CRITICAL PULSE RINGS (expanding/fading circles on critical systems) ---
    if (layers.anomalies) {
      for (const mp of markerPos) {
        const { sys, px, py } = mp
        if (sys.critical === 0) continue
        if (px < -80 || px > w + 80 || py < -80 || py > h + 80) continue

        const color = SEVERITY_COLORS.critical
        const r = parseInt(color.slice(1, 3), 16)
        const g = parseInt(color.slice(3, 5), 16)
        const b = parseInt(color.slice(5, 7), 16)

        // Two offset rings for continuous pulse effect
        for (let ring = 0; ring < 2; ring++) {
          const phase = ((ts * 0.0008 + ring * 0.5) % 1)
          const ringRadius = (20 + phase * 60) * transform.scale
          const ringAlpha = (1 - phase) * 0.25
          if (ringAlpha < 0.02) continue

          ctx.beginPath()
          ctx.arc(px, py, ringRadius, 0, Math.PI * 2)
          ctx.strokeStyle = `rgba(${r},${g},${b},${ringAlpha})`
          ctx.lineWidth = 1.5 - phase
          ctx.stroke()
        }
      }
    }

    // --- EVENT MARKERS (animated pulsing) ---
    if (layers.anomalies && events.length) {
      const pulse = (Math.sin((timestamp || 0) * 0.003) + 1) / 2 // 0-1 oscillation

      for (const ev of events) {
        const sx = pad + ev.nx * drawW
        const sy = pad + ev.nz * drawH
        const px = sx * transform.scale + transform.x
        const py = sy * transform.scale + transform.y

        if (px < -30 || px > w + 30 || py < -30 || py > h + 30) continue

        // Age fade: newer events are brighter (0 = now, 86400 = 24h ago)
        const age = now - ev.detected_at
        const ageFactor = Math.max(0.2, 1 - (age / 86400) * 0.8)

        const color = getTypeColor(ev.anomaly_type)
        const r = parseInt(color.slice(1, 3), 16)
        const g = parseInt(color.slice(3, 5), 16)
        const b = parseInt(color.slice(5, 7), 16)

        const baseR = 3 * transform.scale
        const pulseR = baseR * (1.5 + pulse * 1.5)

        // Pulsing outer ring
        ctx.beginPath()
        ctx.arc(px, py, pulseR, 0, Math.PI * 2)
        ctx.strokeStyle = `rgba(${r},${g},${b},${ageFactor * (0.5 - pulse * 0.4)})`
        ctx.lineWidth = 1.5
        ctx.stroke()

        // Core dot
        ctx.beginPath()
        ctx.arc(px, py, baseR, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${r},${g},${b},${ageFactor * (0.6 + pulse * 0.3)})`
        ctx.fill()
      }
    }

    // --- WATCHTOWER: ASSEMBLY MARKERS (diamond shapes) ---
    if (layers.assemblies) {
      const asms = wtAssembliesRef.current
      if (asms.length) {
        const asmSize = Math.max(3, 4 * transform.scale)
        for (const asm of asms) {
          const sx = pad + asm.nx * drawW
          const sy = pad + asm.nz * drawH
          const px = sx * transform.scale + transform.x
          const py = sy * transform.scale + transform.y
          if (px < -10 || px > w + 10 || py < -10 || py > h + 10) continue

          const color = ASSEMBLY_COLORS[asm.state] || ASSEMBLY_COLORS.unknown

          // Diamond shape
          ctx.beginPath()
          ctx.moveTo(px, py - asmSize)
          ctx.lineTo(px + asmSize, py)
          ctx.lineTo(px, py + asmSize)
          ctx.lineTo(px - asmSize, py)
          ctx.closePath()
          ctx.fillStyle = color
          ctx.fill()
          ctx.strokeStyle = color + '80'
          ctx.lineWidth = 0.5
          ctx.stroke()

          // Type label at higher zoom
          if (transform.scale > 2.5 && asm.type) {
            ctx.fillStyle = '#94a3b8'
            ctx.font = `${Math.min(10, Math.max(7, 8 * transform.scale))}px -apple-system, sans-serif`
            ctx.textAlign = 'center'
            ctx.fillText(asm.type, px, py + asmSize + 10)
          }
        }
      }
    }

    // --- WATCHTOWER: TOP KILLERS (threat entity markers) ---
    if (layers.killers) {
      const killers = wtKillersRef.current
      if (killers.length) {
        for (const k of killers) {
          const sx = pad + k.nx * drawW
          const sy = pad + k.nz * drawH
          const px = sx * transform.scale + transform.x
          const py = sy * transform.scale + transform.y
          if (px < -20 || px > w + 20 || py < -20 || py > h + 20) continue

          const size = Math.max(4, 5 * transform.scale)

          // Danger aura
          const auraR = size * 4
          const auraGrad = ctx.createRadialGradient(px, py, 0, px, py, auraR)
          auraGrad.addColorStop(0, 'rgba(239,68,68,0.15)')
          auraGrad.addColorStop(1, 'rgba(239,68,68,0)')
          ctx.fillStyle = auraGrad
          ctx.beginPath()
          ctx.arc(px, py, auraR, 0, Math.PI * 2)
          ctx.fill()

          // Skull marker (filled circle with X)
          ctx.beginPath()
          ctx.arc(px, py, size, 0, Math.PI * 2)
          ctx.fillStyle = '#ef4444'
          ctx.fill()
          ctx.strokeStyle = '#ffffff'
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.moveTo(px - size * 0.5, py - size * 0.5)
          ctx.lineTo(px + size * 0.5, py + size * 0.5)
          ctx.moveTo(px + size * 0.5, py - size * 0.5)
          ctx.lineTo(px - size * 0.5, py + size * 0.5)
          ctx.stroke()

          // Label at zoom > 1.5
          if (transform.scale > 1.5) {
            ctx.fillStyle = '#ef4444'
            ctx.font = `bold ${Math.min(11, 9 * transform.scale)}px -apple-system, sans-serif`
            ctx.textAlign = 'center'
            ctx.fillText(k.display_name, px, py - size - 5)
            ctx.fillStyle = '#fca5a5'
            ctx.font = `${Math.min(9, 8 * transform.scale)}px -apple-system, sans-serif`
            ctx.fillText(`${k.score} kills`, px, py - size - 5 - 12)
          }
        }
      }
    }

    // --- WATCHTOWER: CONFLICT ZONES (contested systems) ---
    if (layers.conflicts) {
      const conflicts = wtConflictsRef.current
      if (conflicts.length) {
        for (const cz of conflicts) {
          const sx = pad + cz.nx * drawW
          const sy = pad + cz.nz * drawH
          const px = sx * transform.scale + transform.x
          const py = sy * transform.scale + transform.y
          if (px < -60 || px > w + 60 || py < -60 || py > h + 60) continue

          const radius = (15 + Math.min(cz.total_kills, 15) * 2) * transform.scale
          const phase = ((ts * 0.0006) % 1)

          // Rotating dashed ring
          ctx.save()
          ctx.translate(px, py)
          ctx.rotate(phase * Math.PI * 2)
          ctx.beginPath()
          ctx.arc(0, 0, radius, 0, Math.PI * 2)
          ctx.strokeStyle = 'rgba(244,114,182,0.4)'
          ctx.lineWidth = 1.5
          ctx.setLineDash([4, 6])
          ctx.stroke()
          ctx.setLineDash([])

          // Counter-rotating inner ring
          ctx.rotate(-phase * Math.PI * 4)
          ctx.beginPath()
          ctx.arc(0, 0, radius * 0.7, 0, Math.PI * 2)
          ctx.strokeStyle = 'rgba(244,114,182,0.25)'
          ctx.lineWidth = 1
          ctx.setLineDash([3, 5])
          ctx.stroke()
          ctx.setLineDash([])
          ctx.restore()

          // Label at zoom > 2.0
          if (transform.scale > 2.0) {
            ctx.fillStyle = '#f472b6'
            ctx.font = `bold ${Math.min(9, 8 * transform.scale)}px -apple-system, sans-serif`
            ctx.textAlign = 'center'
            ctx.fillText('CONTESTED', px, py - radius - 4)
            ctx.fillStyle = '#fda4af'
            ctx.font = `${Math.min(8, 7 * transform.scale)}px -apple-system, sans-serif`
            ctx.fillText(`${cz.attacker_count} factions \u00b7 ${cz.total_kills} kills`, px, py - radius - 4 - 10)
          }
        }
      }
    }

    // --- VIGNETTE (dark edges, draws focus to center) ---
    const vignetteGrad = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.3, w / 2, h / 2, Math.max(w, h) * 0.75)
    vignetteGrad.addColorStop(0, 'rgba(5,5,8,0)')
    vignetteGrad.addColorStop(0.6, 'rgba(5,5,8,0.25)')
    vignetteGrad.addColorStop(1, 'rgba(5,5,8,0.7)')
    ctx.fillStyle = vignetteGrad
    ctx.fillRect(0, 0, w, h)

    // Continue animation loop
    animRef.current = requestAnimationFrame(drawRef.current)
  }, [])

  // Start/stop animation loop — runs once, draw reads from refs
  useEffect(() => {
    drawRef.current = draw
    animRef.current = requestAnimationFrame(draw)
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current)
    }
  }, [draw])

  // Resize observer
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const ro = new ResizeObserver(() => {
      // Redraw handled by animation loop
    })
    ro.observe(container)
    return () => ro.disconnect()
  }, [])

  // Mouse handlers
  const handleMouseMove = useCallback((e) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const t = transformRef.current

    // Drag
    const drag = dragRef.current
    if (drag.dragging) {
      setTransform(prev => ({
        ...prev,
        x: drag.startTx + (e.clientX - drag.startX),
        y: drag.startTy + (e.clientY - drag.startY),
      }))
      return
    }

    // Hit test systems
    const systems = systemsRef.current
    const pad = 60
    const w = rect.width
    const h = rect.height
    const drawW = w - pad * 2
    const drawH = h - pad * 2
    const maxCount = Math.max(...systems.map(s => s.count), 1)

    let hit = null
    for (const sys of systems) {
      const sx = pad + sys.nx * drawW
      const sy = pad + sys.nz * drawH
      const px = sx * t.scale + t.x
      const py = sy * t.scale + t.y
      const radius = (4 + (sys.count / maxCount) * 16) * t.scale
      const dist = Math.sqrt((mx - px) ** 2 + (my - py) ** 2)
      if (dist <= Math.max(radius, 8)) {
        hit = sys
        break
      }
    }

    // Hit test recent events
    let hitEvent = null
    if (!hit) {
      const events = eventsRef.current
      for (const ev of events) {
        const sx = pad + ev.nx * drawW
        const sy = pad + ev.nz * drawH
        const px = sx * t.scale + t.x
        const py = sy * t.scale + t.y
        const dist = Math.sqrt((mx - px) ** 2 + (my - py) ** 2)
        if (dist <= 10) {
          hitEvent = ev
          break
        }
      }
    }

    // Hit test WatchTower assemblies
    let hitAssembly = null
    if (!hit && !hitEvent && layersRef.current.assemblies) {
      const asms = wtAssembliesRef.current
      const asmSize = Math.max(3, 4 * t.scale)
      for (const asm of asms) {
        const sx = pad + asm.nx * drawW
        const sy = pad + asm.nz * drawH
        const px = sx * t.scale + t.x
        const py = sy * t.scale + t.y
        if (Math.abs(mx - px) <= asmSize + 4 && Math.abs(my - py) <= asmSize + 4) {
          hitAssembly = asm
          break
        }
      }
    }

    // Hit test top killers
    let hitKiller = null
    if (!hit && !hitEvent && !hitAssembly && layersRef.current.killers) {
      const killers = wtKillersRef.current
      for (const k of killers) {
        const sx = pad + k.nx * drawW
        const sy = pad + k.nz * drawH
        const px = sx * t.scale + t.x
        const py = sy * t.scale + t.y
        const dist = Math.sqrt((mx - px) ** 2 + (my - py) ** 2)
        if (dist <= 12) {
          hitKiller = k
          break
        }
      }
    }

    // Hit test conflict zones
    let hitConflict = null
    if (!hit && !hitEvent && !hitAssembly && !hitKiller && layersRef.current.conflicts) {
      const conflicts = wtConflictsRef.current
      for (const cz of conflicts) {
        const sx = pad + cz.nx * drawW
        const sy = pad + cz.nz * drawH
        const px = sx * t.scale + t.x
        const py = sy * t.scale + t.y
        const dist = Math.sqrt((mx - px) ** 2 + (my - py) ** 2)
        const radius = (15 + Math.min(cz.total_kills, 15) * 2) * t.scale
        if (dist <= radius) {
          hitConflict = cz
          break
        }
      }
    }

    if (hit) {
      canvas.style.cursor = 'pointer'
      setTooltip({ x: mx, y: my, sys: hit })
    } else if (hitEvent) {
      canvas.style.cursor = 'pointer'
      setTooltip({ x: mx, y: my, event: hitEvent })
    } else if (hitAssembly) {
      canvas.style.cursor = 'pointer'
      setTooltip({ x: mx, y: my, assembly: hitAssembly })
    } else if (hitKiller) {
      canvas.style.cursor = 'pointer'
      setTooltip({ x: mx, y: my, killer: hitKiller })
    } else if (hitConflict) {
      canvas.style.cursor = 'pointer'
      setTooltip({ x: mx, y: my, conflict: hitConflict })
    } else {
      canvas.style.cursor = 'grab'
      setTooltip(null)
    }
  }, [])

  const handleMouseDown = useCallback((e) => {
    const t = transformRef.current
    dragRef.current = {
      dragging: true,
      startX: e.clientX,
      startY: e.clientY,
      startTx: t.x,
      startTy: t.y,
    }
    if (canvasRef.current) canvasRef.current.style.cursor = 'grabbing'
  }, [])

  const handleMouseUp = useCallback(() => {
    dragRef.current.dragging = false
    if (canvasRef.current) canvasRef.current.style.cursor = 'grab'
  }, [])

  // Attach wheel listener with { passive: false } to allow preventDefault
  // React's onWheel is passive by default and ignores preventDefault
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const onWheel = (e) => {
      e.preventDefault()
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      const factor = e.deltaY < 0 ? 1.15 : 0.87
      setTransform(prev => {
        const newScale = Math.max(0.3, Math.min(10, prev.scale * factor))
        const ratio = newScale / prev.scale
        return {
          scale: newScale,
          x: mx - (mx - prev.x) * ratio,
          y: my - (my - prev.y) * ratio,
        }
      })
    }
    canvas.addEventListener('wheel', onWheel, { passive: false })

    // Touch handlers for mobile
    const getTouchDist = (touches) => {
      const dx = touches[0].clientX - touches[1].clientX
      const dy = touches[0].clientY - touches[1].clientY
      return Math.sqrt(dx * dx + dy * dy)
    }
    const getTouchCenter = (touches, rect) => ({
      x: (touches[0].clientX + touches[1].clientX) / 2 - rect.left,
      y: (touches[0].clientY + touches[1].clientY) / 2 - rect.top,
    })

    const onTouchStart = (e) => {
      e.preventDefault()
      const touch = touchRef.current
      if (e.touches.length === 2) {
        touch.active = true
        touch.lastDist = getTouchDist(e.touches)
        const rect = canvas.getBoundingClientRect()
        const center = getTouchCenter(e.touches, rect)
        touch.lastX = center.x
        touch.lastY = center.y
      } else if (e.touches.length === 1) {
        const t = transformRef.current
        dragRef.current = {
          dragging: true,
          startX: e.touches[0].clientX,
          startY: e.touches[0].clientY,
          startTx: t.x,
          startTy: t.y,
        }
      }
    }

    const onTouchMove = (e) => {
      e.preventDefault()
      const touch = touchRef.current
      if (e.touches.length === 2 && touch.active) {
        const dist = getTouchDist(e.touches)
        const rect = canvas.getBoundingClientRect()
        const center = getTouchCenter(e.touches, rect)
        const factor = dist / touch.lastDist
        setTransform(prev => {
          const newScale = Math.max(0.3, Math.min(10, prev.scale * factor))
          const ratio = newScale / prev.scale
          return {
            scale: newScale,
            x: center.x - (center.x - prev.x) * ratio + (center.x - touch.lastX),
            y: center.y - (center.y - prev.y) * ratio + (center.y - touch.lastY),
          }
        })
        touch.lastDist = dist
        touch.lastX = center.x
        touch.lastY = center.y
      } else if (e.touches.length === 1 && dragRef.current.dragging) {
        const drag = dragRef.current
        setTransform(prev => ({
          ...prev,
          x: drag.startTx + (e.touches[0].clientX - drag.startX),
          y: drag.startTy + (e.touches[0].clientY - drag.startY),
        }))
      }
    }

    const onTouchEnd = (e) => {
      touchRef.current.active = false
      dragRef.current.dragging = false
      // Tap to select — if no drag happened
      if (e.changedTouches.length === 1) {
        const rect = canvas.getBoundingClientRect()
        const mx = e.changedTouches[0].clientX - rect.left
        const my = e.changedTouches[0].clientY - rect.top
        const drag = dragRef.current
        const moved = Math.abs(e.changedTouches[0].clientX - drag.startX) + Math.abs(e.changedTouches[0].clientY - drag.startY)
        if (moved < 10) {
          // Hit test
          const t = transformRef.current
          const systems = systemsRef.current
          const pad = 60
          const drawW = rect.width - pad * 2
          const drawH = rect.height - pad * 2
          const maxCount = Math.max(...systems.map(s => s.count), 1)
          for (const sys of systems) {
            const sx = pad + sys.nx * drawW
            const sy = pad + sys.nz * drawH
            const px = sx * t.scale + t.x
            const py = sy * t.scale + t.y
            const radius = (4 + (sys.count / maxCount) * 16) * t.scale
            if (Math.sqrt((mx - px) ** 2 + (my - py) ** 2) <= Math.max(radius, 16)) {
              setSelectedSystem(sys)
              return
            }
          }
          setSelectedSystem(null)
        }
      }
    }

    canvas.addEventListener('touchstart', onTouchStart, { passive: false })
    canvas.addEventListener('touchmove', onTouchMove, { passive: false })
    canvas.addEventListener('touchend', onTouchEnd)

    return () => {
      canvas.removeEventListener('wheel', onWheel)
      canvas.removeEventListener('touchstart', onTouchStart)
      canvas.removeEventListener('touchmove', onTouchMove)
      canvas.removeEventListener('touchend', onTouchEnd)
    }
  }, [loading])

  const handleClick = useCallback(() => {
    if (tooltip?.sys) {
      setSelectedSystem(tooltip.sys)
      if (onSystemSelect) onSystemSelect(tooltip.sys)
    } else if (tooltip?.event) {
      window.location.href = `/anomalies/${tooltip.event.anomaly_id}`
    } else {
      // Clicking empty space clears selection
      setSelectedSystem(null)
    }
  }, [tooltip, onSystemSelect])

  const toggleLayer = (layer) => {
    setLayers(prev => ({ ...prev, [layer]: !prev[layer] }))
  }

  if (loading) return <p className="text-[#a3a3a3]">Loading map data...</p>

  return (
    <div ref={containerRef} className="relative" style={{ height: height || 'calc(100vh - 200px)' }}>
      <canvas
        ref={canvasRef}
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onClick={handleClick}
        style={{ cursor: 'grab', display: 'block' }}
      />
      {tooltip && (
        <div
          className="absolute pointer-events-none bg-[#1a1a1a] border border-[#2a2a2a] px-3 py-2 text-sm"
          style={{
            left: tooltip.x + 12,
            top: tooltip.y - 10,
            zIndex: 10,
          }}
        >
          {tooltip.sys ? (
            <>
              <div className="text-white font-bold">{tooltip.sys.name || tooltip.sys.system_id}</div>
              <div className="text-[#a3a3a3] text-xs mt-1">
                {tooltip.sys.count} anomalies
              </div>
              <div className="flex gap-2 mt-1 text-xs">
                {tooltip.sys.critical > 0 && <span style={{ color: SEVERITY_COLORS.critical }}>C:{tooltip.sys.critical}</span>}
                {tooltip.sys.high > 0 && <span style={{ color: SEVERITY_COLORS.high }}>H:{tooltip.sys.high}</span>}
                {tooltip.sys.medium > 0 && <span style={{ color: SEVERITY_COLORS.medium }}>M:{tooltip.sys.medium}</span>}
                {tooltip.sys.low > 0 && <span style={{ color: SEVERITY_COLORS.low }}>L:{tooltip.sys.low}</span>}
              </div>
              <div className="text-[#6b7280] text-xs mt-1">Click to view</div>
            </>
          ) : tooltip.event ? (
            <>
              <div className="text-white font-bold">{tooltip.event.system_name || tooltip.event.system_id}</div>
              <div className="text-xs mt-1" style={{ color: getTypeColor(tooltip.event.anomaly_type) }}>
                {getTypeName(tooltip.event.anomaly_type)}
              </div>
              <div className="text-[#a3a3a3] text-xs mt-1">
                <span style={{ color: SEVERITY_COLORS[tooltip.event.severity.toLowerCase()] || '#6b7280' }}>
                  {tooltip.event.severity}
                </span>
                {' \u00b7 '}
                {formatAge(tooltip.event.detected_at)}
              </div>
              <div className="text-[#6b7280] text-xs mt-1">Click to view</div>
            </>
          ) : tooltip.assembly ? (
            <>
              <div className="text-white font-bold">{tooltip.assembly.name || tooltip.assembly.system_id}</div>
              <div className="text-xs mt-1 text-[#a3a3a3]">{tooltip.assembly.type}</div>
              <div className="text-xs mt-1" style={{ color: ASSEMBLY_COLORS[tooltip.assembly.state] || '#6b7280' }}>
                {tooltip.assembly.state.toUpperCase()}
              </div>
            </>
          ) : tooltip.killer ? (
            <>
              <div className="text-white font-bold">{tooltip.killer.display_name}</div>
              <div className="text-xs mt-1 text-red-400">THREAT ENTITY</div>
              <div className="text-xs mt-1 text-[#a3a3a3]">
                {tooltip.killer.score} kills &middot; Last seen: {tooltip.killer.system_name}
              </div>
            </>
          ) : tooltip.conflict ? (
            <>
              <div className="text-white font-bold">{tooltip.conflict.system_name}</div>
              <div className="text-xs mt-1 text-pink-400">ACTIVE CONFLICT</div>
              <div className="text-xs mt-1 text-[#a3a3a3]">
                {tooltip.conflict.attacker_count} factions &middot; {tooltip.conflict.total_kills} kills
              </div>
            </>
          ) : null}
        </div>
      )}
      {/* Unified bottom bar — stats + legend + controls */}
      <div className="absolute bottom-0 left-0 right-0 bg-[#0a0a0a]/90 border-t border-[#2a2a2a] px-4 py-1.5 text-xs font-mono flex items-center justify-between gap-4">
        {data?.systems?.length > 0 ? (
          <div className="flex items-center gap-3 md:gap-5 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse" />
              <span className="text-[#22c55e]">LIVE</span>
            </div>
            <span className="text-[#f59e0b] font-bold">{data.systems.reduce((s, sys) => s + sys.count, 0)}</span>
            <span className="text-[#6b7280]">anomalies in</span>
            <span className="text-[#f59e0b] font-bold">{data.systems.length}</span>
            <span className="text-[#6b7280]">systems</span>
            {data.systems.reduce((s, sys) => s + sys.critical, 0) > 0 && (
              <span className="hidden sm:inline" style={{ color: SEVERITY_COLORS.critical }}>{data.systems.reduce((s, sys) => s + sys.critical, 0)} CRIT</span>
            )}
            {data.systems.reduce((s, sys) => s + sys.high, 0) > 0 && (
              <span className="hidden sm:inline" style={{ color: SEVERITY_COLORS.high }}>{data.systems.reduce((s, sys) => s + sys.high, 0)} HIGH</span>
            )}
          </div>
        ) : <div />}
        <div className="flex items-center gap-3 shrink-0">
          {Object.entries(SEVERITY_COLORS).map(([name, color]) => (
            <div key={name} className="hidden sm:flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-full" style={{ background: color }} />
              <span className="text-[#6b7280] capitalize">{name}</span>
            </div>
          ))}
          <button
            onClick={() => setTransform({ x: 0, y: 0, scale: 1 })}
            className="text-[#6b7280] hover:text-white ml-2"
          >
            Reset
          </button>
        </div>
      </div>

      {/* Selected system — appears only when a system is clicked */}
      {selectedSystem && (
        <div className="absolute top-3 left-3 bg-[#111111]/95 border border-[#f59e0b]/40 px-3 py-2 text-xs space-y-1 max-w-[220px]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1">
              <PinButton
                type="system"
                id={selectedSystem.system_id}
                label={selectedSystem.name || selectedSystem.system_id}
                meta={{ count: selectedSystem.count, critical: selectedSystem.critical }}
              />
              <span className="text-white font-bold text-sm">{selectedSystem.name || selectedSystem.system_id}</span>
            </div>
            <button
              onClick={() => setSelectedSystem(null)}
              className="text-[#6b7280] hover:text-white text-sm ml-2"
            >
              &times;
            </button>
          </div>
          <div className="flex gap-2">
            <span className="text-[#a3a3a3]">{selectedSystem.count} anomalies</span>
            {selectedSystem.critical > 0 && <span style={{ color: SEVERITY_COLORS.critical }}>C:{selectedSystem.critical}</span>}
            {selectedSystem.high > 0 && <span style={{ color: SEVERITY_COLORS.high }}>H:{selectedSystem.high}</span>}
            {selectedSystem.medium > 0 && <span style={{ color: SEVERITY_COLORS.medium }}>M:{selectedSystem.medium}</span>}
          </div>
          <a
            href={`/anomalies?system=${selectedSystem.system_id}`}
            className="block text-[#f59e0b] hover:underline"
          >
            View anomalies &rarr;
          </a>
        </div>
      )}

      {/* Layer toggles — compact, top-right */}
      <div className="absolute top-3 right-3 bg-[#111111]/80 border border-[#2a2a2a] px-2 py-1.5 text-[10px] flex gap-3">
        {[
          { key: 'background', label: 'BG' },
          { key: 'anomalies', label: 'Anomalies' },
          { key: 'hotzones', label: 'Kills' },
          { key: 'threat', label: 'Threat' },
          { key: 'gates', label: 'Gates' },
          { key: 'killers', label: 'Killers' },
          { key: 'conflicts', label: 'War' },
          { key: 'territory', label: 'Terr' },
          { key: 'assemblies', label: 'Asm' },
        ].map(({ key, label }) => (
          <label key={key} className="flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              checked={layers[key]}
              onChange={() => toggleLayer(key)}
              className="accent-[#22c55e] w-3 h-3"
            />
            <span className={layers[key] ? 'text-[#22c55e] font-bold' : 'text-[#ef4444]'}>{label}</span>
          </label>
        ))}
      </div>

    </div>
  )
}

function formatAge(timestamp) {
  const seconds = Math.floor(Date.now() / 1000 - timestamp)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

export default function MapView() {
  const [searchParams] = useSearchParams()
  const query = searchParams.get('q') || ''

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-xl font-bold text-[#f59e0b] tracking-wider">
          FRONTIER MAP
        </h1>
        {query && (
          <span className="text-xs text-[#a3a3a3] bg-[#1a1a1a] border border-[#2a2a2a] px-2 py-1 mono">
            {query}
          </span>
        )}
      </div>
      <AnomalyMap />
    </div>
  )
}
