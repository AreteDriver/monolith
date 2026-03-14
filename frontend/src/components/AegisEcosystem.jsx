import { Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi'

const STATS = [
  { value: '621', label: 'TESTS PASSING' },
  { value: '33', label: 'API ENDPOINTS' },
  { value: '1,320+', label: 'ENTITIES INDEXED' },
];

const TAGS = [
  { label: 'LIVE', variant: 'live' },
  { label: 'VERCEL', variant: 'default' },
  { label: 'FASTAPI', variant: 'default' },
  { label: 'AI NARRATIVE', variant: 'default' },
];

const ECOSYSTEM_LINKS = [
  {
    label: 'WatchTower',
    href: 'https://watchtower-evefrontier.fly.dev',
    external: true,
  },
  {
    label: 'Frontier Tribe OS',
    href: 'https://frontier-tribe-os.vercel.app',
    external: true,
  },
  {
    label: 'Map',
    href: '/map',
    external: false,
  },
];

export default function AegisEcosystem() {
  const { data: healthData } = useApi('/api/health')
  const nexusStats = healthData?.nexus_stats

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');

        @keyframes aegis-scan {
          0% { top: -4px; opacity: 0; }
          5% { opacity: 1; }
          95% { opacity: 1; }
          100% { top: 100%; opacity: 0; }
        }

        .aegis-card {
          font-family: 'Rajdhani', sans-serif;
        }

        .aegis-mono {
          font-family: 'Share Tech Mono', monospace;
        }

        .aegis-scan-container {
          position: relative;
          overflow: hidden;
        }

        .aegis-scan-container::after {
          content: '';
          position: absolute;
          top: -4px;
          left: 0;
          right: 0;
          height: 2px;
          background: linear-gradient(90deg, transparent, #7F77DD, transparent);
          animation: aegis-scan 4s ease-in-out infinite;
          pointer-events: none;
        }
      `}</style>

      <section className="aegis-card">
        {/* Section Header */}
        <div className="flex items-center gap-3 mb-4">
          <span
            className="aegis-mono text-xs tracking-[0.2em] font-bold"
            style={{ color: '#CCC9F8' }}
          >
            AEGIS STACK
          </span>
          <div className="flex-1 h-px" style={{ background: '#534AB7' }} />
          <span
            className="aegis-mono text-[10px] tracking-wider px-2 py-0.5 rounded border"
            style={{
              color: '#CCC9F8',
              borderColor: '#534AB7',
              background: '#26215C',
            }}
          >
            CLEARANCE: PUBLIC
          </span>
        </div>

        {/* Dossier Card */}
        <div
          className="aegis-scan-container rounded-lg p-5"
          style={{
            background: '#111111',
            border: '1px solid #2a2a2a',
            borderLeftWidth: '2px',
            borderLeftColor: '#7F77DD',
          }}
        >
          {/* Designation */}
          <div className="mb-1">
            <span className="aegis-mono text-[#6b7280] text-xs">
              DESIGNATION
            </span>
          </div>
          <h3
            className="aegis-mono text-lg tracking-wider mb-0.5"
            style={{ color: '#CCC9F8' }}
          >
            // WATCHTOWER
          </h3>
          <p
            className="text-xs tracking-[0.15em] font-semibold mb-3"
            style={{ color: '#7F77DD' }}
          >
            CHAIN ARCHAEOLOGY + AI INTEL
          </p>

          {/* Clearance Badge */}
          <div className="mb-4">
            <span
              className="aegis-mono text-[10px] tracking-wider px-2 py-0.5 rounded border"
              style={{
                color: '#CCC9F8',
                borderColor: '#534AB7',
                background: '#26215C',
              }}
            >
              AEGIS-01 / ACTIVE
            </span>
          </div>

          {/* Summary */}
          <p className="text-sm leading-relaxed text-[#a3a3a3] mb-5 max-w-2xl">
            The Living Memory of EVE Frontier. Turns raw on-chain behavior into
            identity &mdash; entity dossiers, behavioral fingerprints, earned titles,
            AI narratives, and reputation scoring. Every gate transit, every killmail,
            every entity &mdash; cataloged, analyzed, scored.
          </p>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-4 mb-5">
            {STATS.map((stat) => (
              <div
                key={stat.label}
                className="text-center py-2 rounded"
                style={{ background: 'rgba(127, 119, 221, 0.08)' }}
              >
                <div
                  className="aegis-mono text-base font-bold"
                  style={{ color: '#CCC9F8' }}
                >
                  {stat.value}
                </div>
                <div className="text-[10px] text-[#6b7280] tracking-wider font-semibold">
                  {stat.label}
                </div>
              </div>
            ))}
          </div>

          {/* NEXUS Stats */}
          {nexusStats && (
            <div className="mb-5 border border-[#2a2a2a] rounded p-3" style={{ background: 'rgba(127, 119, 221, 0.04)' }}>
              <div className="text-[10px] text-[#6b7280] tracking-wider font-semibold mb-2">
                NEXUS EVENT FEED
              </div>
              <div className="flex gap-4">
                {nexusStats.events_received != null && (
                  <div className="text-center">
                    <div className="aegis-mono text-sm font-bold" style={{ color: '#CCC9F8' }}>
                      {nexusStats.events_received.toLocaleString()}
                    </div>
                    <div className="text-[10px] text-[#6b7280]">RECEIVED</div>
                  </div>
                )}
                {nexusStats.events_processed != null && (
                  <div className="text-center">
                    <div className="aegis-mono text-sm font-bold" style={{ color: '#CCC9F8' }}>
                      {nexusStats.events_processed.toLocaleString()}
                    </div>
                    <div className="text-[10px] text-[#6b7280]">PROCESSED</div>
                  </div>
                )}
                {nexusStats.last_event_at && (
                  <div className="text-center">
                    <div className="aegis-mono text-sm font-bold" style={{ color: '#CCC9F8' }}>
                      {nexusStats.last_event_at}
                    </div>
                    <div className="text-[10px] text-[#6b7280]">LAST EVENT</div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Tags */}
          <div className="flex flex-wrap gap-2 mb-4">
            {TAGS.map((tag) => (
              <span
                key={tag.label}
                className="aegis-mono text-[10px] tracking-wider px-2 py-0.5 rounded border"
                style={
                  tag.variant === 'live'
                    ? {
                        color: '#9FE1CB',
                        borderColor: '#1D9E75',
                        background: '#04342C',
                      }
                    : {
                        color: '#6b7280',
                        borderColor: '#2a2a2a',
                        background: 'transparent',
                      }
                }
              >
                {tag.label}
              </span>
            ))}
          </div>

          {/* Ecosystem Links */}
          <div className="flex items-center gap-4 mb-3">
            <span className="text-[#6b7280] text-xs">ECOSYSTEM</span>
            {ECOSYSTEM_LINKS.map((link) =>
              link.external ? (
                <a
                  key={link.label}
                  href={link.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="aegis-mono text-xs hover:underline no-underline"
                  style={{ color: '#7F77DD' }}
                >
                  {link.label} &rarr;
                </a>
              ) : (
                <Link
                  key={link.label}
                  to={link.href}
                  className="aegis-mono text-xs hover:underline no-underline"
                  style={{ color: '#7F77DD' }}
                >
                  {link.label} &rarr;
                </Link>
              )
            )}
          </div>

          {/* Access Link */}
          <div className="flex items-center gap-2">
            <span className="text-[#6b7280] text-xs">ACCESS</span>
            <a
              href="https://watchtower-evefrontier.vercel.app"
              target="_blank"
              rel="noopener noreferrer"
              className="aegis-mono text-xs hover:underline no-underline"
              style={{ color: '#7F77DD' }}
            >
              watchtower-evefrontier.vercel.app &rarr;
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
