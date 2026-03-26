# CLAUDE.md — monolith

## Project Overview

Blockchain anomaly detector and bug report engine for EVE Frontier.
Ingests Sui chain events + World API state, runs 18 detection checkers (39 rules),
generates LLM-narrated bug reports, and alerts via Discord/GitHub/webhooks.

## Current State

- **Version**: 0.5.0
- **Tests**: 567 | **Coverage**: 90% (CI gate: 80%)
- **Status**: LIVE on Fly.io + Vercel
- **Chain**: EVE Frontier "Stillness" (Sui testnet)

## Architecture

```
monolith/
├── backend/
│   ├── alerts/          # Discord, GitHub issue auto-filing (DB-backed dedup), webhook dispatch
│   ├── api/             # FastAPI routes (anomalies, reports, objects, stats, submit, systems, orbital-zones)
│   ├── db/              # SQLite schema (21 tables, 33 indexes, WAL mode, FTS5)
│   ├── detection/       # 18 sync checkers + 1 async (PodChecker) via DetectionEngine
│   ├── ingestion/       # Chain polling, event processing, GraphQL enrichment, NEXUS
│   ├── reports/         # Report builder, LLM narrator (Anthropic), markdown/JSON formatter
│   └── warden/          # Autonomous threat verification via Sui read-only RPC queries
├── contracts/sources/   # Move smart contracts (threat_registry)
├── eval/                # Evaluation layer — detection quality, narration scoring, system metrics
├── frontend/src/        # React + Vite SPA (anomaly feed, map, reports)
├── tests/               # pytest (mirrors backend/ structure)
├── demo_seed.py         # Seed DB with labeled demo data for eval + demos
├── fly.toml             # Fly.io deployment config
└── pyproject.toml       # Python packaging + tool config
```

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLite (WAL), Anthropic SDK
- **Frontend**: React, Vite, Tailwind CSS
- **Chain**: Sui RPC (JSON-RPC + GraphQL), EVE Frontier World API
- **Infra**: Docker, Fly.io, Vercel, GitHub Actions
- **Tools**: ruff (lint + format), pytest, pytest-cov

## Common Commands

```bash
# test
pytest tests/ -x -q --cov=backend --cov-fail-under=80

# lint + format (always run BOTH)
ruff check backend/ tests/ eval/
ruff format backend/ tests/ eval/

# seed demo data + run eval
python demo_seed.py --db monolith.db
python eval/detection_quality.py --db monolith.db --fail-on-regression
python eval/narration_eval.py --db monolith.db --verbose
python eval/system_metrics.py --db monolith.db

# run server
python -m uvicorn backend.main:app --reload

# deploy
/home/arete/.fly/bin/flyctl deploy --wait-timeout 600
```

## Database Schema (Key Tables)

| Table | Purpose |
|-------|---------|
| `chain_events` | Raw Sui events (event_id, event_type, object_id, raw_json, cycle) |
| `objects` | Tracked objects + current state/owner/system |
| `anomalies` | Detected anomalies (type, severity, category, evidence_json, status, cycle) |
| `bug_reports` | Generated reports (plain_english, evidence, input_tokens, output_tokens) |
| `detection_cycles` | Cycle timing for eval (started_at, finished_at, anomalies_found) |
| `item_ledger` | Economic tracking (deposits, withdrawals per assembly) |
| `subscriptions` | Webhook subscribers with severity/type filters |
| `orbital_zones` | Orbital zones with feral AI tier + threat level tracking |
| `feral_ai_events` | Feral AI events (entity, type, zone, severity) |

**Migrations**: `init_db()` in `database.py` runs idempotent ALTER TABLE for new columns on existing DBs.

## Detection Engine

- **Entry**: `DetectionEngine.run_cycle()` in `backend/detection/engine.py`
- **Checkers**: 18 sync (registered in `_register_all_checkers`) + PodChecker (async, Sui GraphQL)
- **Dedup**: `(anomaly_type, object_id)` within 24h window
- **Anomaly ID**: `MNLT-YYYYMMDD-XXXX` with `os.urandom(3).hex()` suffix on collision
- **Cycle recording**: Each cycle writes timing to `detection_cycles` table
- **GitHub dedup**: DB-backed (filed_issues JOIN anomalies) — survives process restarts

## Warden System

- **Entry**: `Warden.run_cycle()` in `backend/warden/warden.py`
- **Purpose**: Autonomous threat verification — reads UNVERIFIED anomalies, queries Sui chain, marks VERIFIED/DISMISSED
- **Sui queries**: `backend/warden/sui_queries.py` — get_object_state, verify_object_exists, get_dynamic_fields
- **Guardrails**: Max cycle limit (default 24), read-only chain access, chain health check before each cycle

## LLM Narration

- **File**: `backend/reports/llm_narrator.py`
- **Returns**: `dict` with keys `narration`, `input_tokens`, `output_tokens`
- **API**: `anthropic.AsyncAnthropic`, claude-sonnet-4-5, max_tokens=100
- **Fallback**: Template narrations in `TEMPLATES` dict (27 anomaly types)
- **Voice**: Terse frontier intelligence analyst, 2-3 sentences, <50 words

## Eval Layer

Three scripts in `eval/` measure system quality:

| Script | What it measures | CI gate? |
|--------|-----------------|----------|
| `detection_quality.py` | Precision/recall/F1 per checker vs ground truth | Yes (`--fail-on-regression`) |
| `narration_eval.py` | Factual grounding, severity alignment, actionability, hallucination | Informational (needs API key) |
| `system_metrics.py` | P50/P95 latency, anomaly rate, cost/report, poll drift | No (operational) |

**Ground truth**: `EVAL_GROUND_TRUTH` in `detection_quality.py` must match `demo_seed.py` anomalies.

## Background Loops (main.py)

| Loop | Interval | Purpose |
|------|----------|---------|
| `chain_poll_loop` | 30s | Poll Sui events → chain_events → object state |
| `snapshot_loop` | 15min | Compute state deltas between snapshots |
| `detection_loop` | 5min | Run all 18 sync checkers, alert on CRITICAL/HIGH |
| `pod_check_loop` | 5min | Async PodChecker + KillmailChecker |
| `graphql_enrichment_loop` | 1h | Location, versions, configs, wallet profiles |
| `static_data_loop` | 1h | Systems, types, tribes from World API |
| `table_prune_loop` | 6h | Garbage collect old world_states + state_transitions |
| `warden_loop` | 5min | Autonomous threat verification (UNVERIFIED → VERIFIED/DISMISSED) |

## Configuration

All settings via env vars with `MONOLITH_` prefix (pydantic-settings):

| Var | Default | Purpose |
|-----|---------|---------|
| `MONOLITH_CHAIN` | `stillness` | Chain environment (stillness/nova) |
| `MONOLITH_DATABASE_PATH` | `monolith.db` | SQLite path |
| `MONOLITH_SUI_PACKAGE_ID` | (auto-fetch) | Move package ID |
| `MONOLITH_ANTHROPIC_API_KEY` | (empty) | LLM narration |
| `MONOLITH_DISCORD_WEBHOOK_URL` | (empty) | Alert channel |
| `MONOLITH_GITHUB_REPO` | (empty) | Auto-file issues |

## Coding Standards

- **Naming**: snake_case (Python), camelCase (JS/TS)
- **Quotes**: double quotes
- **Type hints**: required on all functions
- **Docstrings**: Google style
- **Imports**: absolute (`from backend.x.y import Z`)
- **Paths**: `pathlib.Path` (never `os.path`)
- **Line length**: 100 chars (ruff config)
- **Logging**: `logging` module (never `print()`)
- **Error handling**: specific exceptions, never bare `except:`
- **SQLite**: `check_same_thread=False` for FastAPI cross-thread usage
- **Async**: `asynccontextmanager` for FastAPI lifespan (not `contextmanager`)

## Anti-Patterns (Do NOT Do)

- Do NOT commit secrets or API keys — use `MONOLITH_*` env vars
- Do NOT use `os.path` — use `pathlib.Path`
- Do NOT use bare `except:` — catch specific exceptions
- Do NOT use `print()` for logging — use `logging` module
- Do NOT use `latest` Docker tags — pin versions
- Do NOT skip tests for new code
- Do NOT use mutable default arguments
- Do NOT call `narrate_anomaly()` expecting a string — it returns a dict

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | System health + row counts |
| GET | `/api/anomalies` | List anomalies (filters: severity, type, status) |
| GET | `/api/anomalies/{id}` | Anomaly detail |
| POST | `/api/anomalies/bulk/status` | Bulk status update |
| GET | `/api/reports` | List bug reports |
| GET | `/api/reports/{id}` | Report detail (json/markdown/text) |
| POST | `/api/reports/generate` | Generate report from anomaly |
| GET | `/api/objects` | List tracked objects |
| GET | `/api/stats` | Anomaly counts by severity/type |
| GET | `/api/systems/map` | Map data (systems + anomalies) |
| POST | `/api/submit` | Player-reported anomaly submission |
| POST | `/api/nexus/webhook` | NEXUS event ingestion |
| GET | `/api/orbital-zones` | List orbital zones (filters: system_id, threat_level) |
| GET | `/api/orbital-zones/threats` | Threat level aggregation across zones |
| GET | `/api/orbital-zones/feral-ai/events` | Feral AI event feed |
| GET | `/api/orbital-zones/cycle` | Current universe cycle metadata |

## Dependencies

### Core
fastapi, uvicorn, httpx, pydantic, pydantic-settings, anthropic, aiosqlite, slowapi

### Dev
pytest, pytest-asyncio, pytest-cov, ruff, respx

## Git Conventions

- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`
- Branch naming: `feat/description`, `fix/description`
- Run `pytest tests/ -x -q` + `ruff check` before pushing
- CI gates: lint, format, 80% coverage, eval detection quality
