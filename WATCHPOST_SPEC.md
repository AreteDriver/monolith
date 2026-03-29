# Watchpost Feature Spec — Bidirectional Intel Nodes

**Status**: Planned (2026-03-28)
**Deadline**: March 31, 2026 (hackathon)
**Purpose**: In-game SSU nodes that consume AND produce WatchTower intel

---

## Competitive Context

- **FrontierOps** (enfarious): Fully decentralized operator console — jobs/bounty escrow, assembly management, AI mission control, in-game embed. No analytical depth.
- **Frontier Overwatch**: Galaxy intel dashboard + Intel Beacon SSU mod (crowd-sourced scouting). Most direct competitor.
- **Monolith + WatchTower**: Intelligence pipeline (39 detection rules, Warden autonomous verification, eval layer). Watchposts neutralize Frontier Overwatch's Intel Beacon differentiator.

---

## New Tables

```sql
CREATE TABLE watchposts (
    watchpost_id TEXT PRIMARY KEY,        -- WP-{system_id}-{short_hash}
    system_id TEXT NOT NULL,
    owner_wallet TEXT NOT NULL,
    assembly_id TEXT,                      -- SSU object ID if known
    registered_at INTEGER NOT NULL,
    last_ping INTEGER NOT NULL,
    status TEXT DEFAULT 'active'          -- active | silent | decommissioned
);
CREATE INDEX idx_watchposts_system ON watchposts(system_id);
CREATE INDEX idx_watchposts_status ON watchposts(status);

CREATE TABLE watchpost_reports (
    report_id TEXT PRIMARY KEY,           -- WPR-YYYYMMDD-{hex}
    watchpost_id TEXT NOT NULL,
    system_id TEXT NOT NULL,
    report_type TEXT NOT NULL,            -- hostile_spotted | gate_camp | fleet_movement | fuel_warning | all_clear
    details TEXT,
    reporter_wallet TEXT NOT NULL,
    reported_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    FOREIGN KEY (watchpost_id) REFERENCES watchposts(watchpost_id)
);
CREATE INDEX idx_wpr_system ON watchpost_reports(system_id);
CREATE INDEX idx_wpr_expires ON watchpost_reports(expires_at);
```

---

## New Endpoints — `backend/api/watchposts.py`

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/watchposts/register` | Register SSU as watchpost (wallet + system_id + assembly_id) |
| POST | `/api/v1/watchposts/ping` | Heartbeat |
| GET | `/api/v1/watchposts/{system_id}/intel` | Pull local intel (anomalies + reports + kills) |
| POST | `/api/v1/watchposts/report` | Submit sighting report |
| GET | `/api/v1/watchposts/network` | All active watchposts (map layer) |
| DELETE | `/api/v1/watchposts/{watchpost_id}` | Decommission |

### Intel Response Shape

```json
{
  "system_id": "30000142",
  "system_name": "...",
  "threat_level": "HIGH",
  "anomalies": [],
  "reports": [],
  "nearby_kills": [],
  "active_watchposts": 3,
  "last_updated": 1711612815
}
```

---

## Detection Integration

**WatchpostChecker (rule WP1):**
- Correlates player reports with chain events
- 2+ watchposts in nearby systems report hostiles AND killmails confirm → elevated threat, VERIFIED
- Report with no corroborating chain data after TTL → expires silently
- Reports also feed into existing OrbitalZoneChecker threat levels

---

## SSU Behavior Panel — `watchpost.html`

Single standalone HTML/JS file served from GitHub Pages.

```
┌─────────────────────────────────┐
│  WATCHPOST — System 30000142    │
│  Status: ● ACTIVE               │
├─────────────────────────────────┤
│  LOCAL INTEL                     │
│  ⚠ 2 anomalies (1 HIGH)        │
│  👁 1 hostile report (12m ago)  │
│  💀 3 kills nearby (1h)         │
├─────────────────────────────────┤
│  REPORT SIGHTING                │
│  [Hostile] [Gate Camp] [Fleet]  │
│  [Fuel Warning] [All Clear]     │
│  Details: [_______________]     │
│  [SUBMIT REPORT]                │
├─────────────────────────────────┤
│  NETWORK: 7 watchposts active   │
│  Last ping: 2m ago              │
└─────────────────────────────────┘
```

- Auto-registers on first load (wallet from SSU context)
- Pings every 5 minutes
- Polls intel every 60 seconds
- One-tap report submission
- No auth beyond wallet address

---

## Map Layer (MapView.jsx)

- Watchpost icons (radar dish)
- Color: green (active + recent ping), yellow (stale), gray (silent)
- Click shows local intel summary
- Player reports as temporary markers (fade on expiry)

---

## Implementation Order

**Day 1 — Backend:**
- Tables in database.py
- Router: watchposts.py
- Wire into main.py
- Tests

**Day 2 — Frontend + SSU Panel:**
- watchpost.html
- Map layer in MapView.jsx
- WatchpostChecker (WP1)

**Day 3 — Demo + Deploy:**
- Deploy to Fly.io
- Record demo video
- Watchpost flow: deploy → see intel → report → propagate
