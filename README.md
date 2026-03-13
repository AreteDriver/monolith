# MONOLITH

**Blockchain Integrity Monitor for EVE Frontier**

Monolith continuously reads EVE Frontier's on-chain Sui events, detects state anomalies that indicate bugs or unintended behavior, and generates structured bug reports with on-chain evidence that CCP and Sui engineers can act on immediately.

---

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/AreteDriver/monolith.git
cd monolith
cp .env.example .env
# Edit .env to add API keys (optional)
docker compose up
# Open http://localhost:8000
```

### Local Development

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Seed demo data
python demo_seed.py

# Run backend
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
python -m pytest -v
```

---

## What It Does

### Detection Engine

17 deterministic rules across 4 checkers detect chain anomalies:

| Checker | Rules | Detects |
|---------|-------|---------|
| **Continuity** | C1-C4 | Orphan objects, resurrection, state gaps, stuck objects |
| **Economic** | E1-E4 | Supply discrepancy, unexplained destruction, duplicate mint, negative balance |
| **Assembly** | A1, A4-A5 | Contract/API mismatch, phantom changes, ownership without transfer |
| **Sequence** | S2, S4 | Duplicate transactions, block processing gaps |

Rules are pure functions: `(events, states) -> anomaly | None`. No ML, no guesswork. Every detection is auditable and reproducible.

### Bug Reports

Each anomaly generates a structured report with:
- Severity classification (CRITICAL/HIGH/MEDIUM/LOW)
- Self-contained evidence (no joins needed)
- Chain transaction references (Sui txDigest)
- Reproduction context (detector, rule, observation window)
- Recommended investigation steps
- Plain English summary (Anthropic API or template fallback)

Output formats: Markdown, JSON, Plain Text.

### Alerts

CRITICAL and HIGH severity anomalies fire Discord webhook embeds immediately, rate-limited to 5/minute.

---

## Architecture

```
Sui Chain (suix_queryEvents) ─┐
                              ▼
                   ┌─────────────┐
                   │  Ingestion  │  chain_reader (Sui), state_snapshotter
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │   SQLite    │  chain_events, world_states, objects,
                   │  WAL+FTS5  │  state_transitions, anomalies, bug_reports
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │  Detection  │  4 checkers, 17 rules, 24h deduplication
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │   Reports   │  builder + LLM narrator + formatter
                   └──────┬──────┘
                          ▼
               ┌──────────┴──────────┐
               ▼                     ▼
        ┌─────────────┐     ┌──────────────┐
        │  FastAPI     │     │  React +     │
        │  REST API    │     │  Tailwind UI │
        └─────────────┘     └──────────────┘
               │
               ▼
        Discord Webhooks
```

### Tech Stack

| Layer | Choice |
|-------|--------|
| Backend | FastAPI + uvicorn |
| Database | SQLite WAL + FTS5 |
| Chain | Sui testnet RPC (suix_queryEvents) |
| Detection | Pure Python rule engine |
| LLM | Anthropic API (narration only, never detection) |
| Frontend | React + Tailwind + Recharts |
| Alerts | Discord webhooks |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | System health, uptime, row counts |
| GET | `/api/anomalies` | List anomalies (filter: severity, type, status) |
| GET | `/api/anomalies/{id}` | Anomaly detail with evidence |
| GET | `/api/reports` | List bug reports |
| GET | `/api/reports/{id}` | Report in json/markdown/text format |
| POST | `/api/reports/generate` | Generate report from anomaly |
| GET | `/api/objects/{id}` | Object state trail + transitions |
| GET | `/api/objects` | Search/list tracked objects |
| GET | `/api/stats` | Anomaly rates, breakdowns, system health |
| POST | `/api/submit` | Player bug submission with chain evidence |

---

## Configuration

All settings via environment variables (prefix `MONOLITH_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `monolith.db` | SQLite database path |
| `ANTHROPIC_API_KEY` | *(empty)* | Enables LLM narration |
| `DISCORD_WEBHOOK_URL` | *(empty)* | Enables Discord alerts |
| `SUI_PACKAGE_ID` | *(empty)* | Sui Move package ID (required for live data) |
| `SUI_RPC_URL` | `https://fullnode.testnet.sui.io:443` | Sui RPC endpoint |
| `CHAIN_POLL_INTERVAL` | `30` | Chain event poll interval (seconds) |
| `DETECTION_INTERVAL` | `300` | Detection cycle interval (seconds) |

---

## Demo Flow

1. **Landing page** — Live stats, detection rules, architecture overview
2. **Anomaly Feed** — Real-time list with severity colors and CRITICAL pulse
3. **Anomaly Detail** — Full evidence block, chain references, generate report
4. **Bug Report** — Formatted report with copy/download, plain English summary
5. **Object Tracker** — Paste any ID, see full chain history
6. **Stats Dashboard** — Hourly rates, severity pie, type breakdown, system heatmap
7. **Player Submit** — Self-service bug submission with chain evidence lookup

---

## Project Structure

```
monolith/
├── backend/
│   ├── main.py                — FastAPI app + background tasks
│   ├── config.py              — Settings (env vars)
│   ├── db/database.py         — SQLite WAL + schema
│   ├── ingestion/             — Chain + World API + snapshotter
│   ├── detection/             — 4 checkers + engine + scorer
│   ├── reports/               — Builder + LLM narrator + formatter
│   ├── alerts/discord.py      — Discord webhook alerts
│   └── api/                   — REST endpoints
├── frontend/                  — React + Tailwind + Recharts
├── tests/                     — 118 pytest tests
├── docs/chain-samples/        — Real API response samples
├── demo_seed.py               — Seed demo data
├── Dockerfile                 — Multi-stage build
├── docker-compose.yml         — One-command deploy
└── CLAUDE.md                  — AI context file
```

---

## Why This Matters

The Sui migration is the hardest thing CCP has done technically. Moving a live game's economy to a new chain while players are still playing is an enormous engineering challenge.

Monolith is a QA tool for that migration. Every bug it finds before launch is a player who doesn't lose their assets to a contract error.

**Monolith doesn't just find bugs. It makes them impossible to ignore.**

---

*Built by [AreteDriver](https://github.com/AreteDriver) for the EVE Frontier x Sui Hackathon 2026*
