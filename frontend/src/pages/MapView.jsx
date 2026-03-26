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

function AnomalyMap() {
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
  const [layers, setLayers] = useState({ background: true, heatmap: true, events: true, markers: true })
  const layersRef = useRef(layers)

  const { data, loading } = useApi('/api/stats/map', { poll: 60000 })
  // Background systems are static — fetch once, cache in browser
  const { data: bgData } = useApi('/api/stats/map/systems', { poll: 0 })

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

  // Keep refs synced with state
  useEffect(() => { transformRef.current = transform }, [transform])
  useEffect(() => { layersRef.current = layers }, [layers])

  const draw = useCallback((timestamp) => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

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
    ctx.fillStyle = '#0a0a0a'
    ctx.fillRect(0, 0, w, h)

    // Grid
    ctx.strokeStyle = '#222222'
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

    // Scanline sweep effect
    const scanY = ((timestamp || 0) * 0.03) % h
    const scanGrad = ctx.createLinearGradient(0, scanY - 30, 0, scanY + 30)
    scanGrad.addColorStop(0, 'rgba(245,158,11,0)')
    scanGrad.addColorStop(0.5, 'rgba(245,158,11,0.03)')
    scanGrad.addColorStop(1, 'rgba(245,158,11,0)')
    ctx.fillStyle = scanGrad
    ctx.fillRect(0, scanY - 30, w, 60)

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

    // --- BACKGROUND SYSTEMS (dim dots for full universe) ---
    if (layers.background && bgSystems.length) {
      ctx.fillStyle = '#334155'
      for (const sys of bgSystems) {
        const sx = pad + sys.nx * drawW
        const sy = pad + sys.nz * drawH
        const px = sx * transform.scale + transform.x
        const py = sy * transform.scale + transform.y

        if (px < -5 || px > w + 5 || py < -5 || py > h + 5) continue

        ctx.beginPath()
        ctx.arc(px, py, Math.max(1.5, 2 * transform.scale), 0, Math.PI * 2)
        ctx.fill()
      }

      // Labels at higher zoom
      if (transform.scale > 2.5) {
        ctx.fillStyle = '#334155'
        ctx.font = `${Math.max(8, 9 * transform.scale)}px -apple-system, sans-serif`
        ctx.textAlign = 'center'
        for (const sys of bgSystems) {
          const sx = pad + sys.nx * drawW
          const sy = pad + sys.nz * drawH
          const px = sx * transform.scale + transform.x
          const py = sy * transform.scale + transform.y
          if (px < -5 || px > w + 5 || py < -5 || py > h + 5) continue
          if (sys.name) ctx.fillText(sys.name, px, py - 5 * transform.scale)
        }
      }
    }
    const maxCount = systems.length ? Math.max(...systems.map(s => s.count)) : 1
    const now = Date.now() / 1000

    // --- HEATMAP LAYER ---
    if (layers.heatmap) {
      // Use globalCompositeOperation for additive blending
      ctx.save()
      ctx.globalCompositeOperation = 'lighter'

      for (const sys of systems) {
        const sx = pad + sys.nx * drawW
        const sy = pad + sys.nz * drawH
        const px = sx * transform.scale + transform.x
        const py = sy * transform.scale + transform.y

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

    // --- SYSTEM MARKERS ---
    if (layers.markers) {
      for (const sys of systems) {
        const sx = pad + sys.nx * drawW
        const sy = pad + sys.nz * drawH
        const px = sx * transform.scale + transform.x
        const py = sy * transform.scale + transform.y

        if (px < -20 || px > w + 20 || py < -20 || py > h + 20) continue

        const severity = getMaxSeverity(sys)
        const color = SEVERITY_COLORS[severity]
        const baseRadius = 4 + (sys.count / maxCount) * 16
        const radius = baseRadius * transform.scale

        // Glow
        ctx.beginPath()
        ctx.arc(px, py, radius * 2.5, 0, Math.PI * 2)
        const glow = ctx.createRadialGradient(px, py, 0, px, py, radius * 2.5)
        glow.addColorStop(0, color + '40')
        glow.addColorStop(1, color + '00')
        ctx.fillStyle = glow
        ctx.fill()

        // Dot
        ctx.beginPath()
        ctx.arc(px, py, radius, 0, Math.PI * 2)
        ctx.fillStyle = color
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

        // Label for large dots
        if (radius > 6 * transform.scale && sys.name) {
          ctx.fillStyle = '#e0e0e0'
          ctx.font = `${Math.max(9, 11 * transform.scale)}px -apple-system, sans-serif`
          ctx.textAlign = 'center'
          ctx.fillText(sys.name, px, py - radius - 4)
        }
      }
    }

    // --- EVENT MARKERS (animated pulsing) ---
    if (layers.events && events.length) {
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

    if (hit) {
      canvas.style.cursor = 'pointer'
      setTooltip({ x: mx, y: my, sys: hit })
    } else if (hitEvent) {
      canvas.style.cursor = 'pointer'
      setTooltip({ x: mx, y: my, event: hitEvent })
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
  }, [])

  const handleClick = useCallback(() => {
    if (tooltip?.sys) {
      setSelectedSystem(tooltip.sys)
    } else if (tooltip?.event) {
      window.location.href = `/anomalies/${tooltip.event.anomaly_id}`
    }
  }, [tooltip])

  const toggleLayer = (layer) => {
    setLayers(prev => ({ ...prev, [layer]: !prev[layer] }))
  }

  if (loading) return <p className="text-[#a3a3a3]">Loading map data...</p>

  return (
    <div ref={containerRef} className="relative" style={{ height: 'calc(100vh - 200px)' }}>
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
          { key: 'heatmap', label: 'Heat' },
          { key: 'events', label: 'Events' },
          { key: 'markers', label: 'Markers' },
        ].map(({ key, label }) => (
          <label key={key} className="flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              checked={layers[key]}
              onChange={() => toggleLayer(key)}
              className="accent-[#f59e0b] w-3 h-3"
            />
            <span className={layers[key] ? 'text-[#e0e0e0]' : 'text-[#6b7280]'}>{label}</span>
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
