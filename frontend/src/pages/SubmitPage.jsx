import { useState } from 'react'
import { Link } from 'react-router-dom'
import SeverityBadge from '../components/SeverityBadge'

export default function SubmitPage() {
  const [objectId, setObjectId] = useState('')
  const [objectType, setObjectType] = useState('')
  const [description, setDescription] = useState('')
  const [characterName, setCharacterName] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!objectId.trim()) return

    setLoading(true)
    setResult(null)

    try {
      const res = await fetch('/api/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          object_id: objectId.trim(),
          object_type: objectType,
          observed_at: Math.floor(Date.now() / 1000),
          description: description.trim(),
          character_name: characterName.trim(),
        }),
      })
      const data = await res.json()
      setResult(data)
    } catch {
      setResult({ status: 'error', message: 'Failed to submit. Check network.' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-2">Submit Bug Report</h1>
      <p className="text-sm text-[#a3a3a3] mb-6">
        Paste an object ID and describe what you observed. Monolith will pull chain
        evidence and check for anomalies.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4 mb-8">
        <div>
          <label className="block text-xs text-[#6b7280] uppercase mb-1">
            Object ID *
          </label>
          <input
            type="text"
            value={objectId}
            onChange={(e) => setObjectId(e.target.value)}
            placeholder="0x..."
            required
            className="w-full bg-[#1a1a1a] border border-[#2a2a2a] text-[#e5e5e5] px-3 py-2 mono text-sm"
          />
        </div>

        <div>
          <label className="block text-xs text-[#6b7280] uppercase mb-1">
            Object Type
          </label>
          <select
            value={objectType}
            onChange={(e) => setObjectType(e.target.value)}
            className="bg-[#1a1a1a] border border-[#2a2a2a] text-[#e5e5e5] px-3 py-2 text-sm"
          >
            <option value="">Unknown</option>
            <option value="SmartGate">Smart Gate</option>
            <option value="SmartStorageUnit">Storage Unit</option>
            <option value="SmartTurret">Smart Turret</option>
            <option value="NetworkNode">Network Node</option>
            <option value="Manufacturing">Manufacturing</option>
            <option value="character">Character</option>
          </select>
        </div>

        <div>
          <label className="block text-xs text-[#6b7280] uppercase mb-1">
            What did you observe?
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g., My gate consumed fuel but didn't teleport me..."
            rows={3}
            className="w-full bg-[#1a1a1a] border border-[#2a2a2a] text-[#e5e5e5] px-3 py-2 text-sm resize-y"
          />
        </div>

        <div>
          <label className="block text-xs text-[#6b7280] uppercase mb-1">
            Character Name (optional)
          </label>
          <input
            type="text"
            value={characterName}
            onChange={(e) => setCharacterName(e.target.value)}
            className="bg-[#1a1a1a] border border-[#2a2a2a] text-[#e5e5e5] px-3 py-2 text-sm w-64"
          />
        </div>

        <button
          type="submit"
          disabled={loading || !objectId.trim()}
          className="bg-[#f59e0b] text-black px-6 py-2 text-sm font-bold cursor-pointer hover:bg-[#d97706] disabled:opacity-50 border-none"
        >
          {loading ? 'Finding Evidence...' : 'Find Evidence'}
        </button>
      </form>

      {/* Result */}
      {result && (
        <div className="border border-[#2a2a2a] p-4">
          {result.status === 'anomaly_found' && (
            <div>
              <div className="flex items-center gap-3 mb-3">
                <SeverityBadge severity={result.severity} />
                <span className="mono text-sm text-[#f59e0b]">{result.anomaly_type}</span>
                <span className="text-sm text-green-400 font-bold">Anomaly Detected</span>
              </div>
              <p className="text-sm text-[#a3a3a3] mb-3">
                Monolith found a {result.anomaly_type} anomaly. A full bug report has
                been generated with chain evidence attached.
              </p>
              {result.report_id && (
                <Link
                  to={`/reports/${result.report_id}`}
                  className="bg-[#f59e0b] text-black px-4 py-2 text-sm font-bold no-underline hover:bg-[#d97706]"
                >
                  View Report
                </Link>
              )}
            </div>
          )}

          {result.status === 'no_anomaly_detected' && (
            <div>
              <div className="text-sm text-[#a3a3a3] mb-3">
                <span className="text-yellow-400 font-bold">No Rule Violation Detected</span>
                <p className="mt-2">{result.message}</p>
              </div>
              {result.events_in_window?.length > 0 && (
                <div className="mt-3">
                  <h3 className="text-xs text-[#6b7280] uppercase mb-2">
                    Chain Events in Window ({result.events_in_window.length})
                  </h3>
                  <pre className="mono text-xs bg-[#111111] p-3 overflow-x-auto">
                    {JSON.stringify(result.events_in_window, null, 2)}
                  </pre>
                </div>
              )}
              {result.events_in_window?.length === 0 && (
                <p className="text-xs text-[#6b7280]">
                  No chain events found for this object in the ±30 minute window.
                </p>
              )}
            </div>
          )}

          {result.status === 'error' && (
            <p className="text-red-400 text-sm">{result.message}</p>
          )}
        </div>
      )}
    </div>
  )
}
