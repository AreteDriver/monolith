# CLAUDE.md — monolith

## Project Overview

Blockchain Integrity Monitor for EVE Frontier. Continuously reads on-chain Sui events via `suix_queryEvents`, detects anomalies via 17 deterministic rules across 4 checkers, and generates structured bug reports. Built for EVE Frontier x Sui Hackathon 2026 (deadline March 31, 2026).

## Current State

- **Version**: 0.1.0
- **Language**: Python
- **Files**: 107 across 4 languages
- **Lines**: 12,320

## Architecture

```
monolith/
├── backend/
│   ├── alerts/
│   ├── api/
│   ├── db/
│   ├── detection/
│   ├── ingestion/
│   └── reports/
├── docs/
│   └── chain-samples/
├── frontend/
│   ├── .vercel/
│   ├── public/
│   └── src/
├── tests/
│   ├── test_alerts/
│   ├── test_api/
│   ├── test_db/
│   ├── test_detection/
│   ├── test_ingestion/
│   └── test_reports/
├── .dockerignore
├── .env.example
├── .gitignore
├── CLAUDE.md
├── Dockerfile
├── README.md
├── demo_seed.py
├── docker-compose.yml
├── explore_chain.py
├── fly.toml
├── pyproject.toml
```

## Tech Stack

- **Language**: Python, JavaScript, HTML, CSS
- **Framework**: fastapi
- **Package Manager**: pip
- **Linters**: ruff
- **Formatters**: ruff
- **Test Frameworks**: pytest
- **Runtime**: Docker

## Coding Standards

- **Naming**: snake_case
- **Quote Style**: double quotes
- **Type Hints**: present
- **Imports**: absolute
- **Path Handling**: pathlib
- **Line Length (p95)**: 79 characters

## Common Commands

```bash
# test
pytest tests/ -v

# lint + format
ruff check backend/ tests/ && ruff format backend/ tests/

# run locally
python -m uvicorn backend.main:app --reload --port 8000

# seed demo data
python demo_seed.py

# build frontend
cd frontend && npm run build

# deploy
/home/arete/.fly/bin/flyctl deploy -a monolith-evefrontier
```

## Chain (Sui)

- **Sui RPC**: `https://fullnode.testnet.sui.io:443` (configurable via `MONOLITH_SUI_RPC_URL`)
- **Package ID**: Set via `MONOLITH_SUI_PACKAGE_ID` env var (changes each cycle)
- **Event query**: `suix_queryEvents` with cursor-based pagination (`sui_cursors` table)
- **Polling**: Chain events 30s, Snapshots 900s, Detection 300s

## Detection Rules

| Checker | Rules | Detects |
|---------|-------|---------|
| Continuity | C1-C4 | Orphan objects, resurrection, state gaps, stuck objects |
| Economic | E1-E4 | Supply discrepancy, unexplained destruction, duplicate mint, negative balance |
| Assembly | A1,A4,A5 | Contract/API mismatch, phantom changes, ownership without transfer |
| Sequence | S2,S4 | Duplicate transactions, block processing gaps |

Rules are pure functions: `(events, states) → anomaly | None`. Deterministic, no ML.

## Anti-Patterns (Do NOT Do)

- Do NOT commit secrets, API keys, or credentials
- Do NOT skip writing tests for new code
- Do NOT hardcode secrets in Dockerfiles — use environment variables
- Do NOT use `latest` tag — pin specific versions
- Do NOT use synchronous database calls in async endpoints
- Do NOT return raw dicts — use Pydantic response models
- Do NOT use `os.path` — use `pathlib.Path` everywhere
- Do NOT use bare `except:` — catch specific exceptions
- Do NOT use mutable default arguments
- Do NOT use `print()` for logging — use the `logging` module

## Dependencies

### Core
- fastapi
- uvicorn

### Dev
- pytest
- pytest-asyncio
- pytest-cov
- ruff
- respx

## Domain Context

### Key Models/Classes
- `Anomaly`
- `AssemblyChecker`
- `BaseChecker`
- `ChainReader`
- `ContinuityChecker`
- `DetectionEngine`
- `EconomicChecker`
- `EventStream`
- `FakeSettings`
- `SequenceChecker`
- `Settings`
- `StateSnapshotter`
- `SubmitRequest`
- `WorldPoller`
- `ReportBuilder`

### Domain Terms
- **Smart Assembly** — EVE Frontier on-chain object (gates, storage units, turrets, etc.)
- **Sui** — Layer 1 blockchain, EVE Frontier's chain since Cycle 5 (March 2026)
- **Package ID** — Sui Move package address, changes each cycle
- **txDigest** — Sui transaction hash identifier
- **parsedJson** — Decoded Move event data in Sui event responses

### API Endpoints
- `GET /api/health` — uptime, last block, row counts
- `GET /api/anomalies` — list (severity/type/status filters)
- `GET /api/anomalies/{id}` — detail with evidence
- `GET /api/reports` — list reports
- `GET /api/reports/{id}` — report in JSON/Markdown/Text
- `POST /api/reports/generate` — generate from anomaly
- `GET /api/objects/{id}` — state trail + transitions
- `GET /api/objects` — search tracked objects
- `GET /api/stats` — rates, severity distribution, heatmap
- `POST /api/submit` — player bug submission
- `GET /api/submit/{id}/status` — submission status

### Environment Variables
- `MONOLITH_DATABASE_PATH` — SQLite path (default: `monolith.db`)
- `MONOLITH_SUI_PACKAGE_ID` — Sui Move package ID (required for live chain data)
- `MONOLITH_SUI_RPC_URL` — Sui RPC endpoint (default: testnet)
- `MONOLITH_CHAIN_POLL_INTERVAL` — Chain poll interval seconds (default: 30)
- `MONOLITH_ANTHROPIC_API_KEY` — optional, enables LLM narration
- `MONOLITH_DISCORD_WEBHOOK_URL` — optional, enables alerts (rate-limited 5/min)

## Deployment

- **Backend**: Fly.io (`monolith-evefrontier`), shared CPU 256MB, persistent SQLite at `/data/monolith.db`
- **Frontend**: Vercel (`monolith-evefrontier.vercel.app`)
- **Note**: `min_machines_running = 1` to keep chain pollers alive

## Git Conventions

- Commit messages: Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`)
- Branch naming: `feat/description`, `fix/description`
- Run tests before committing
