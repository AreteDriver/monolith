import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApi } from '../hooks/useApi'

const SEVERITY_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#6b7280',
}

const TYPE_COLORS = {
  POD_MISMATCH: '#ef4444',
  CONTINUITY_BREAK: '#f97316',
  SEQUENCE_GAP: '#a855f7',
  ECONOMIC_ANOMALY: '#3b82f6',
  ASSEMBLY_DRIFT: '#10b981',
  KILLMAIL_ANOMALY: '#ec4899',
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
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 })
  const dragRef = useRef({ dragging: false, startX: 0, startY: 0, startTx: 0, startTy: 0 })
  const systemsRef = useRef([])
  const eventsRef = useRef([])
  const animRef = useRef(null)
  const [layers, setLayers] = useState({ heatmap: true, events: true, markers: true })

  const { data, loading } = useApi('/api/stats/map', { poll: 60000 })

  // Compute normalized positions once when data arrives
  useEffect(() => {
    if (!data?.systems?.length) {
      systemsRef.current = []
      eventsRef.current = []
      return
    }
    const systems = data.systems
    const allPoints = [...systems, ...(data.recent_events || [])]
    const xs = allPoints.map(s => s.x)
    const zs = allPoints.map(s => s.z)
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minZ = Math.min(...zs)
    const maxZ = Math.max(...zs)
    const rangeX = maxX - minX || 1
    const rangeZ = maxZ - minZ || 1

    systemsRef.current = systems.map(s => ({
      ...s,
      nx: (s.x - minX) / rangeX,
      nz: (s.z - minZ) / rangeZ,
    }))

    eventsRef.current = (data.recent_events || []).map(e => ({
      ...e,
      nx: (e.x - minX) / rangeX,
      nz: (e.z - minZ) / rangeZ,
    }))
  }, [data])

  const draw = useCallback((timestamp) => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

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
    ctx.strokeStyle = '#1a1a1a'
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

    const systems = systemsRef.current
    const events = eventsRef.current
    if (!systems.length) {
      ctx.fillStyle = '#6b7280'
      ctx.font = '14px -apple-system, sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('No anomaly data available', w / 2, h / 2)
      return
    }

    const pad = 60
    const drawW = w - pad * 2
    const drawH = h - pad * 2
    const maxCount = Math.max(...systems.map(s => s.count))
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
    animRef.current = requestAnimationFrame(draw)
  }, [transform, layers])

  // Start/stop animation loop
  useEffect(() => {
    animRef.current = requestAnimationFrame(draw)
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current)
    }
  }, [draw, data])

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
      const px = sx * transform.scale + transform.x
      const py = sy * transform.scale + transform.y
      const radius = (4 + (sys.count / maxCount) * 16) * transform.scale
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
        const px = sx * transform.scale + transform.x
        const py = sy * transform.scale + transform.y
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
  }, [transform])

  const handleMouseDown = useCallback((e) => {
    dragRef.current = {
      dragging: true,
      startX: e.clientX,
      startY: e.clientY,
      startTx: transform.x,
      startTy: transform.y,
    }
    if (canvasRef.current) canvasRef.current.style.cursor = 'grabbing'
  }, [transform])

  const handleMouseUp = useCallback(() => {
    dragRef.current.dragging = false
    if (canvasRef.current) canvasRef.current.style.cursor = 'grab'
  }, [])

  const handleWheel = useCallback((e) => {
    e.preventDefault()
    const rect = canvasRef.current.getBoundingClientRect()
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
  }, [])

  const handleClick = useCallback(() => {
    if (tooltip?.sys) {
      window.location.href = `/anomalies?system=${tooltip.sys.system_id}`
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
        onWheel={handleWheel}
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
                {tooltip.event.anomaly_type.replace(/_/g, ' ')}
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
      {/* Legend */}
      <div className="absolute bottom-4 left-4 bg-[#111111]/90 border border-[#2a2a2a] px-3 py-2 text-xs space-y-2">
        <div className="text-[#a3a3a3] font-bold uppercase mb-1">Severity</div>
        {Object.entries(SEVERITY_COLORS).map(([name, color]) => (
          <div key={name} className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full" style={{ background: color }} />
            <span className="text-[#a3a3a3] capitalize">{name}</span>
          </div>
        ))}
        <div className="border-t border-[#2a2a2a] mt-2 pt-2">
          <div className="text-[#a3a3a3] font-bold uppercase mb-1">Event Types</div>
          {Object.entries(TYPE_COLORS).map(([name, color]) => (
            <div key={name} className="flex items-center gap-2">
              <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: color }} />
              <span className="text-[#6b7280]">{name.replace(/_/g, ' ').toLowerCase()}</span>
            </div>
          ))}
        </div>
      </div>
      {/* Layer controls */}
      <div className="absolute top-4 right-4 bg-[#111111]/90 border border-[#2a2a2a] px-3 py-2 text-xs space-y-1.5">
        <div className="text-[#a3a3a3] font-bold uppercase mb-1">Layers</div>
        {[
          { key: 'heatmap', label: 'Heatmap' },
          { key: 'events', label: 'Events (24h)' },
          { key: 'markers', label: 'System Markers' },
        ].map(({ key, label }) => (
          <label key={key} className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={layers[key]}
              onChange={() => toggleLayer(key)}
              className="accent-[#f59e0b]"
            />
            <span className={layers[key] ? 'text-[#e0e0e0]' : 'text-[#6b7280]'}>{label}</span>
          </label>
        ))}
      </div>
      {/* Controls */}
      <div className="absolute bottom-4 right-4 flex gap-2">
        <button
          onClick={() => setTransform({ x: 0, y: 0, scale: 1 })}
          className="bg-[#111111] border border-[#2a2a2a] text-[#a3a3a3] hover:text-white px-3 py-1 text-xs"
        >
          Reset
        </button>
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

function EfMapEmbed({ query }) {
  const embedUrl = query
    ? `https://ef-map.com/embed?q=${encodeURIComponent(query)}`
    : 'https://ef-map.com/embed'

  return (
    <div className="border border-[#2a2a2a] overflow-hidden" style={{ height: 'calc(100vh - 200px)' }}>
      <iframe
        src={embedUrl}
        title="EVE Frontier Map"
        width="100%"
        height="100%"
        style={{ border: 'none' }}
        allowFullScreen
      />
    </div>
  )
}

export default function MapView() {
  const [searchParams] = useSearchParams()
  const query = searchParams.get('q') || ''
  const [tab, setTab] = useState('anomalies')

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-[#f59e0b] tracking-wider">
            FRONTIER MAP
          </h1>
          {query && (
            <span className="text-xs text-[#a3a3a3] bg-[#1a1a1a] border border-[#2a2a2a] px-2 py-1 mono">
              {query}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setTab('anomalies')}
            className={`text-xs px-3 py-1 border ${
              tab === 'anomalies'
                ? 'border-[#f59e0b] text-[#f59e0b] bg-[#1a1a1a]'
                : 'border-[#2a2a2a] text-[#6b7280] hover:text-[#a3a3a3]'
            }`}
          >
            Anomaly Map
          </button>
          <button
            onClick={() => setTab('efmap')}
            className={`text-xs px-3 py-1 border ${
              tab === 'efmap'
                ? 'border-[#f59e0b] text-[#f59e0b] bg-[#1a1a1a]'
                : 'border-[#2a2a2a] text-[#6b7280] hover:text-[#a3a3a3]'
            }`}
          >
            EF-Map
          </button>
        </div>
      </div>
      {tab === 'anomalies' ? <AnomalyMap /> : <EfMapEmbed query={query} />}
    </div>
  )
}
