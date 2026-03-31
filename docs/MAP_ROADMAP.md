# Monolith Map — Intelligence Visualization Roadmap

**Style**: 3D Three.js galaxy (locked in). Dark, clean, sci-fi command center.
**Principle**: The map IS the intel. Every visual element tells part of the story. If it doesn't convey intelligence, it doesn't belong.

---

## Architecture: Layered Intelligence

Each layer is independently toggleable. Clicking any element on any layer opens a contextual intel card.

### Layer 1 — Spatial Reference (Base)
- [x] 24K system star field as galaxy disc
- [x] Grid plane for depth reference
- [x] Nebula gas clouds for atmosphere
- [ ] System names on hover (not just anomaly systems)
- [ ] Constellation boundaries (faint region borders)
- [ ] Region labels at low zoom

### Layer 2 — Activity Heat (Where things happen)
- [x] Kill zone beams (hotzones from WatchTower)
- [ ] **Heat gradient on galactic plane** — continuous color field, not discrete markers. Red = high kill density, blue = quiet. Computed from hotzone data spread across nearby systems
- [ ] **Temporal heat** — toggle 24h / 7d / 30d to see activity shift over time
- [ ] Animated kill events — brief flash + expanding ring when a new kill occurs (WebSocket or polling)

### Layer 3 — Entity Presence (Who is there)
- [x] Top killers positioned at last known system
- [ ] **Entity markers as distinct icons** — skull for killers, shield for corps, diamond for assemblies. Not just colored dots
- [ ] **Corp territory shading** — convex hull mesh around systems where a corp has majority kills/assemblies. Semi-transparent, corp-colored
- [ ] **Entity trails** — fading path lines showing an entity's movement history across systems (last N killmail locations)
- [ ] **Assembly infrastructure** — gate icons, storage units, refineries as distinct 3D shapes at their system locations

### Layer 4 — Threat Intelligence (What's dangerous)
- [x] Anomaly markers with severity coloring + bloom
- [x] Danger rings on critical/high systems
- [x] Selection beacon on clicked system
- [ ] **Anomaly type clustering** — group anomalies by type (economic, continuity, engagement) with distinct visual signatures
- [ ] **Threat corridors** — highlight routes between high-threat systems as danger zones
- [ ] **Predictive overlay** — WatchTower threat forecast as gradient heat, showing where danger is EXPECTED to escalate
- [ ] **Warden verification status** — visual distinction between UNVERIFIED (pulsing) vs VERIFIED (solid) vs DISMISSED (dim)

### Layer 5 — Connections (How things relate)
- [x] Movement route arcs between systems
- [ ] **Animated particle flow** — particles moving along route lines showing direction of travel
- [ ] **Transaction flow** — MIST transfer arrows between systems, thickness = volume. Follow the money
- [ ] **Kill graph edges** — lines between killer and victim home systems, showing who is hunting whom
- [ ] **Gate network** — once gate-to-system mapping is resolved, show actual gate transit routes
- [ ] **Alliance/rivalry indicators** — colored connection lines between corp territory centers (green = allied, red = hostile)

---

## Intel Card System

Every clickable element opens a contextual card. Cards should be:
- **Compact** — fits in corner, doesn't obscure map
- **Contextual** — shows different data based on what was clicked
- **Actionable** — links to drill-down (anomaly detail, WatchTower dossier, entity profile)

### Card Types
- [x] **System Card** — anomaly count, kills, threat level, dominant faction, nearby threats
- [ ] **Entity Card** — kill count, danger rating, behavioral fingerprint summary, last N systems visited
- [ ] **Assembly Card** — type, state, owner, fuel status, nearby threats
- [ ] **Route Card** — transit count, who uses this route, danger along the path
- [ ] **Anomaly Card** — type, severity, evidence summary, Warden verification status

### Card Drill-Down
- [x] "View Anomalies" link to anomaly feed
- [x] "WatchTower" link to full system/entity dossier
- [ ] Inline mini-timeline (last 5 events at this location)
- [ ] "Watch this" button — set up NEXUS alert for this system/entity

---

## Performance Targets

| Metric | Current | Target |
|--------|---------|--------|
| Initial load | ~2s | <1.5s |
| 60fps at 24K systems | Yes | Maintain |
| Points clickable | Yes (raycasting) | Maintain |
| Max simultaneous markers | ~50 | 200+ (instanced mesh) |
| Data refresh | 60s polling | 30s + WebSocket for kills |

### Optimization Path
- [ ] InstancedMesh for anomaly markers (single draw call for all)
- [ ] InstancedMesh for kill flash markers
- [ ] Frustum culling for labels (only render visible ones)
- [ ] LOD — reduce detail at distance
- [ ] WebSocket for real-time kill events (eliminate polling lag)

---

## Data Sources

| Layer | Source | Refresh |
|-------|--------|---------|
| Systems | `/api/stats/map/systems` | Static (ETag) |
| Anomalies | `/api/stats/map` | 60s poll |
| Hotzones | WatchTower `/hotzones` | 60s via overlay |
| Killers | WatchTower `/leaderboard/top_killers` | 60s via overlay |
| Routes | Computed from `nexus_events` killmail topology | 60s via overlay |
| Territory | Derived from hotzone dominance | 60s via overlay |
| Conflicts | Derived from multi-attacker hotzones | 60s via overlay |
| Threat forecast | WatchTower `/predictions/map` | 60s via overlay |
| Assemblies | WatchTower `/assemblies` | 60s via overlay |
| Entity dossiers | WatchTower `/entity/{id}` | On demand (click) |
| Transactions | WatchTower `/transfers` | Future |
| Kill graph | WatchTower `/kill-graph` | Future |

---

## Priority Order

### Phase 1 — Demo Ready (current)
Everything checked above. Map works, shows fused intel, clickable systems, selection beacon.

### Phase 2 — Story Layer
- Heat gradient on galactic plane
- Entity markers as distinct icons
- Animated particle flow on routes
- Inline mini-timeline in cards

### Phase 3 — Full Intelligence
- Corp territory convex hulls
- Entity movement trails
- Transaction flow visualization
- Kill graph edges
- Real-time kill events via WebSocket

### Phase 4 — Command Center
- Constellation/region boundaries
- Predictive threat overlay
- "Watch this" alert button
- Multiple simultaneous cards
- Keyboard navigation (arrow keys to cycle through systems)
