# MONOLITH

**Blockchain anomaly detector and bug report engine for EVE Frontier.**

Monolith ingests 13 Sui on-chain event types in real time, runs 31 deterministic detection rules against them, and surfaces bugs with full chain evidence — so CCP and Sui engineers can fix issues before players lose assets.

> **Live demo**: [monolith-evefrontier.fly.dev](https://monolith-evefrontier.fly.dev/)

---

## What Judges Will See

1. **Landing page** — Live ingestion stats, detection rule inventory, system health
2. **Anomaly Feed** — Real-time detections with severity badges (CRITICAL pulses red)
3. **Real-time Map** — Canvas2D rendering of 24,502 solar systems with heatmap overlay, animated event markers, crosshair reticles, and a stats HUD. Anomaly hotspots glow
4. **Anomaly Detail** — Click any anomaly to see full evidence: chain tx references, object states, rule explanation
5. **Bug Reports** — One-click generation with plain English summary, Markdown/JSON/text export
6. **Item Ledger** — Economic tracking across mint, transfer, and destruction events
7. **Stats Dashboard** — Hourly detection rates, severity breakdown, type distribution
8. **Public API** — `/v1/` endpoints return JSON. Webhook subscriptions push anomalies to external consumers

---

## Features

- **13 Sui event types** ingested via `suix_queryEvents` + GraphQL enrichment
- **35 detection rules** across 17 checkers — zero ML, fully deterministic and auditable
- **Canvas2D map** — 24,502 systems, scanline-sweep heatmap, animated markers, 60fps
- **Item ledger** — tracks mints, transfers, destructions for economic integrity
- **POD verification** — validates Provable Object Datatypes against chain state
- **Auto-filed GitHub issues** for CRITICAL anomalies
- **Discord alerting** — webhook embeds for CRITICAL/HIGH, rate-limited
- **Webhook subscriptions** — push anomaly events to any HTTP endpoint
- **Public API v1** — read anomalies, stats, health, object history
- **241 tests passing**

### Detection Rules

| Checker | Rules | Detects |
|---------|-------|---------|
| **Continuity** | C1-C4 | Orphan objects, resurrection, state gaps, stuck objects |
| **Economic** | E1-E4 | Supply discrepancy, unexplained destruction, duplicate mint, negative balance |
| **Assembly** | A1-A5 | Contract/API mismatch, toll runners, gate tax loss, phantom changes, silent seizure |
| **Sequence** | S1-S4 | Broken ledger, duplicate ingestion, sequence drift, block gaps |
| **POD** | P1 | Chain divergence — local state vs on-chain truth |
| **Killmail** | K1-K2 | Duplicate kills, third-party kill reporters |
| **Coordinated Buying** | CB1-CB2 | Fleet staging signals, clustered wallet activity |
| **Object Version** | OV1-OV2 | State rollbacks, unauthorized modifications |
| **Wallet Concentration** | WC1 | Monopoly detection, asset hoarding |
| **Config Change** | CC1 | Game config modifications (Energy/Fuel/Gate) |
| **Inventory Audit** | IA1 | Conservation-of-mass violations |
| **Bot Pattern** | BP1 | Automated transaction patterns |
| **Tribe Hopping** | TH1 | Rapid corp changes (spy detection) |
| **Engagement Session** | ES1-ES2 | Orphaned killmails, ghost victims |
| **Dead Assembly** | DA1 | Abandoned infrastructure (7+ days silent) |
| **Velocity** | EV1-EV2 | Flow rate spikes, sudden activity drops |
| **Ownership** | OC1 | OwnerCap transfers and delegation detection |

Every rule is a pure function: `(events, states) -> anomaly | None`. No guesswork. Every detection ships with chain tx digests for independent verification.

---

## Architecture

```
Sui Testnet (suix_queryEvents)
         │
         ▼
┌─────────────────┐     ┌──────────────┐
│   Chain Reader   │────▶│  GraphQL     │
│  (13 event types)│     │  Enrichment  │
└────────┬────────┘     └──────┬───────┘
         │                      │
         ▼                      ▼
┌──────────────────────────────────────┐
│          SQLite WAL + FTS5           │
│  chain_events │ objects │ anomalies  │
│  world_states │ ledger  │ bug_reports│
└────────────────┬─────────────────────┘
                 │
         ┌───────┴───────┐
         ▼               ▼
┌─────────────┐  ┌──────────────┐
│  Detection  │  │  Item Ledger │
│  Engine     │  │  (economic)  │
│  17 checkers │  └──────────────┘
│  35 rules   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Reports   │──▶ GitHub Issues (CRITICAL)
│  + Alerts   │──▶ Discord Webhooks
│  + Webhooks │──▶ Subscriber Endpoints
└──────┬──────┘
       │
  ┌────┴─────┐
  ▼          ▼
FastAPI    React + Canvas2D
REST API   Real-time Map + UI
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python, FastAPI, uvicorn |
| Database | SQLite WAL + FTS5 |
| Chain | Sui testnet RPC (`suix_queryEvents`) + GraphQL |
| Detection | Pure Python rule engine (no ML) |
| Map | React + Canvas2D (scanline heatmap, 24K systems) |
| Frontend | React, Tailwind CSS, Recharts |
| Alerts | Discord webhooks, GitHub API |
| Hosting | Fly.io (backend), Vercel (frontend) |

---

## Getting Started

### Docker (fastest)

```bash
git clone https://github.com/AreteDriver/monolith.git
cd monolith
cp .env.example .env
docker compose up
# Open http://localhost:8000
```

### Local Development

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python demo_seed.py          # seed demo data
python -m uvicorn backend.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

### Run Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
# 241 tests passing
```

---

## API Endpoints

### Public API (`/v1/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/health` | System health, uptime, ingestion stats |
| GET | `/v1/anomalies` | List anomalies (filter: severity, type, status) |
| GET | `/v1/anomalies/{id}` | Full anomaly detail with chain evidence |
| GET | `/v1/stats` | Detection rates, severity breakdown |

### Internal API (`/api/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/anomalies` | Anomaly list with pagination |
| GET | `/api/reports` | Bug report list |
| POST | `/api/reports/generate` | Generate report from anomaly |
| GET | `/api/objects/{id}` | Object state trail + transitions |
| GET | `/api/stats/map` | Map data (24,502 systems + anomaly overlay) |
| GET | `/api/stats/ledger` | Item ledger entries |
| POST | `/api/subscriptions` | Register webhook subscription |
| DELETE | `/api/subscriptions/{id}` | Remove webhook subscription |
| POST | `/api/submit` | Player bug submission with chain evidence |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONOLITH_SUI_PACKAGE_ID` | — | Sui Move package ID (required for live chain) |
| `MONOLITH_SUI_RPC_URL` | `https://fullnode.testnet.sui.io:443` | Sui RPC endpoint |
| `MONOLITH_DATABASE_PATH` | `monolith.db` | SQLite database path |
| `MONOLITH_ANTHROPIC_API_KEY` | — | Enables LLM narration on reports |
| `MONOLITH_DISCORD_WEBHOOK_URL` | — | Enables Discord alerts |
| `MONOLITH_CHAIN_POLL_INTERVAL` | `30` | Chain poll interval (seconds) |
| `MONOLITH_DETECTION_INTERVAL` | `300` | Detection cycle interval (seconds) |

---

## Why This Matters

EVE Frontier runs a live game economy on Sui. Every smart assembly, gate jump, killmail, and item transfer is an on-chain transaction. When something breaks — an item duplicates, a gate resurrects after destruction, a transfer creates value from nothing — players lose real assets.

Monolith watches the chain continuously and catches these bugs with cryptographic proof. It doesn't guess. It shows the exact transaction digests, the before/after states, and the rule that fired. CRITICAL anomalies auto-file GitHub issues so nothing gets lost.

**16,500+ chain events ingested. 309+ anomalies detected. 35 rules. 17 checkers. Zero false positive tolerance.**

---

## Aegis Stack

Monolith is the detection layer of the **Aegis Stack** — a unified toolkit for EVE Frontier civilization.

| Layer | Project | What It Does |
|-------|---------|-------------|
| **Intelligence** | [WatchTower](https://github.com/AreteDriver/watchtower) | Behavioral fingerprints, reputation scoring, alt detection, kill networks, on-chain reputation oracle |
| **Detection** | [Monolith](https://github.com/AreteDriver/monolith) (this repo) | 35 anomaly detection rules, 17 checkers, threat heatmap, auto-filed bug reports with chain evidence |
| **Operations** | [Frontier Tribe OS](https://github.com/AreteDriver/frontier-tribe-os) | Tribe management — census, production, treasury, intel, alerts, threat analysis |

**Combined**: 1,227+ tests | 3 live deployments | On-chain Sui Move contracts | 24,502 systems mapped | Dual payment rails (Sui + Stripe)

- [WatchTower Live Demo](https://watchtower-evefrontier.vercel.app/)
- [Monolith Live Demo](https://monolith-evefrontier.fly.dev/)
- [Frontier Tribe OS Live Demo](https://frontend-ten-theta-80.vercel.app)

---

*Aegis Stack — Built by [AreteDriver](https://github.com/AreteDriver) for the DeepSurge Hackathon 2026*
