/**
 * Pinnable Intel — localStorage-backed pin system.
 *
 * Pin types: 'anomaly', 'system', 'filter'
 * Storage: localStorage('monolith_pins')
 * No auth required, instant, offline-capable.
 */
import { useState, useEffect, useCallback } from 'react'

const STORAGE_KEY = 'monolith_pins'
const MAX_PINS = 50

function loadPins() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function savePins(pins) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pins.slice(0, MAX_PINS)))
  } catch {
    // localStorage full or unavailable
  }
}

// Broadcast channel for cross-tab sync
let channel = null
try {
  channel = new BroadcastChannel('monolith_pins')
} catch {
  // BroadcastChannel not available
}

export function usePins() {
  const [pins, setPins] = useState(loadPins)

  // Listen for cross-tab updates
  useEffect(() => {
    if (!channel) return
    const handler = () => setPins(loadPins())
    channel.addEventListener('message', handler)
    return () => channel.removeEventListener('message', handler)
  }, [])

  const addPin = useCallback((pin) => {
    setPins((prev) => {
      // Dedupe by type + id
      if (prev.some((p) => p.type === pin.type && p.id === pin.id)) return prev
      const next = [{ ...pin, pinned_at: Date.now() }, ...prev]
      savePins(next)
      channel?.postMessage('update')
      return next
    })
  }, [])

  const removePin = useCallback((type, id) => {
    setPins((prev) => {
      const next = prev.filter((p) => !(p.type === type && p.id === id))
      savePins(next)
      channel?.postMessage('update')
      return next
    })
  }, [])

  const isPinned = useCallback(
    (type, id) => pins.some((p) => p.type === type && p.id === id),
    [pins]
  )

  const clearPins = useCallback(() => {
    savePins([])
    setPins([])
    channel?.postMessage('update')
  }, [])

  return { pins, addPin, removePin, isPinned, clearPins }
}
