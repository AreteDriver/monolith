import { useEffect, useState } from 'react'

const WT_API = 'https://watchtower-evefrontier.fly.dev/api'
const cache = {}

export function useSystemNames(systemIds) {
  const [names, setNames] = useState({})

  const idsKey = systemIds.filter(Boolean).join(',')

  useEffect(() => {
    const ids = [...new Set(systemIds.filter(Boolean))]
    if (ids.length === 0) return

    // Check if all IDs already have server-enriched names or are cached
    const uncached = ids.filter((id) => !(id in cache))
    if (uncached.length === 0) {
      setNames({ ...cache })
      return
    }

    async function resolve() {
      // Try batch resolve from our backend first
      try {
        const res = await fetch(`/api/systems/resolve?ids=${uncached.join(',')}`)
        if (res.ok) {
          const data = await res.json()
          // data expected as { "id": "name", ... } or { systems: { "id": "name" } }
          const mapping = data.systems || data
          for (const id of uncached) {
            if (mapping[id]) {
              cache[id] = mapping[id]
            }
          }
        }
      } catch {
        // Batch endpoint unavailable, fall through
      }

      // Fall back to WatchTower individual lookups for any still-uncached IDs
      const stillUncached = uncached.filter((id) => !(id in cache))
      if (stillUncached.length > 0) {
        await Promise.allSettled(
          stillUncached.map((id) =>
            fetch(`${WT_API}/system/${id}`)
              .then((r) => r.json())
              .then((d) => {
                cache[id] = d.solar_system_name || null
              })
              .catch(() => {
                cache[id] = null
              })
          )
        )
      }

      setNames({ ...cache })
    }

    resolve()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey])

  return names
}

/**
 * Pre-populate cache from server-enriched anomaly data.
 * Call this before useSystemNames to avoid unnecessary lookups.
 */
export function primeSystemNameCache(anomalies) {
  if (!Array.isArray(anomalies)) return
  for (const a of anomalies) {
    if (a.system_id && a.system_name && !(a.system_id in cache)) {
      cache[a.system_id] = a.system_name
    }
  }
}
