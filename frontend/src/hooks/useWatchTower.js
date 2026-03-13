import { useEffect, useState } from 'react'

const WT_API = 'https://watchtower-evefrontier.fly.dev/api'
const cache = {}

export function useSystemNames(systemIds) {
  const [names, setNames] = useState({})

  useEffect(() => {
    const ids = [...new Set(systemIds.filter(Boolean))]
    if (ids.length === 0) return

    const uncached = ids.filter((id) => !(id in cache))
    if (uncached.length === 0) {
      setNames({ ...cache })
      return
    }

    Promise.allSettled(
      uncached.map((id) =>
        fetch(`${WT_API}/system/${id}`)
          .then((r) => r.json())
          .then((d) => {
            cache[id] = d.solar_system_name || null
          })
          .catch(() => {
            cache[id] = null
          })
      )
    ).then(() => setNames({ ...cache }))
  }, [systemIds.join(',')])

  return names
}
