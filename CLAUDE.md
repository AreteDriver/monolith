# Monolith — Blockchain Anomaly Detector for EVE Frontier

## What This Is
Blockchain integrity monitor for EVE Frontier. Reads on-chain events and World API state, detects anomalies, generates structured bug reports for CCP/Sui engineers.

## Tech Stack
- **Backend**: FastAPI + uvicorn, Python 3.11+
- **Database**: SQLite WAL + FTS5
- **Chain**: OP Sepolia (current) → Sui (pending migration)
- **World API**: `blockchain-gateway-stillness.live.tech.evefrontier.com` (v2 endpoints)
- **Detection**: Pure Python rule engine (deterministic, auditable)
- **LLM**: Anthropic API (claude-sonnet-4-5) — narration ONLY, never detection
- **Frontend**: React + Tailwind
- **Alerts**: Discord webhooks

## Chain State (March 2026)
- **Current chain**: OP Sepolia (chain ID 11155420) with MUD framework
- **Sui migration**: In progress but NOT live yet
- **World contract**: `0x1dacc0b64b7da0cc6e2b2fe1bd72f58ebd37363c`
- Architecture supports both chains — detection rules are chain-agnostic

## Key URLs
- World API: `https://blockchain-gateway-stillness.live.tech.evefrontier.com`
- Chain RPC: `https://op-sepolia-ext-sync-node-rpc.live.tech.evefrontier.com`
- Block Explorer: `https://sepolia-optimism.etherscan.io`
- Old URLs (DEAD): `*.nursery.reitnorf.com` — all replaced by `*.live.tech.evefrontier.com`

## World API Data (v2 endpoints)
- `/v2/smartassemblies` — 35,808 items (NetworkNode, Manufacturing, SmartGate, SmartTurret, SmartStorageUnit)
- `/v2/smartcharacters` — 5,172 characters
- `/v2/killmails` — 4,853 kill records
- `/v2/tribes` — 47 tribes
- `/v2/solarsystems` — 24,502 systems
- `/v2/types` — 336 item types
- `/v2/fuels` — 6 fuel types

## Assembly Fields (from API)
- List: `id, type, name, state, solarSystem{id,name}, owner{address,name,id}, energyUsage, typeId`
- Detail adds: `typeDetails, description, dappURL, location{x,y,z}, networkNode{fuel,burn,energy}`
- States: `unanchored`, `online`, `offline`, `anchored`
- Types: `NetworkNode`, `Manufacturing`, `SmartGate`, `SmartTurret`, `SmartStorageUnit`

## MUD System IDs (from /config)
Key contract calls: `createCharacter`, `bringOnline`, `bringOffline`, `depositFuel`,
`withdrawFuel`, `destroyDeployable`, `unanchor`, `reportKill`, `transfer`,
`createAndDepositItemsToInventory`, `withdrawFromInventory`

## Architecture Principles
- Detection rules are pure functions: `(events, states) → anomaly | None`
- Never mutate source data — anomalies table is append-only
- Evidence is self-contained in the anomaly record — no joins needed to render a report
- Severity is deterministic from rule — no LLM in the detection path
- LLM is only used for plain English narration AFTER detection
- False positive rate matters — rules must have low noise
- Prefer false negatives over false positives

## Project Structure
```
monolith/
├── backend/
│   ├── main.py              — FastAPI app entry
│   ├── config.py            — Settings (env vars)
│   ├── db/
│   │   └── database.py      — SQLite setup, schema, WAL
│   ├── ingestion/
│   │   ├── chain_reader.py  — OP Sepolia RPC + log reader
│   │   ├── world_poller.py  — World API v2 REST polling
│   │   ├── event_stream.py  — MUD event stream (placeholder)
│   │   └── state_snapshotter.py — periodic state deltas
│   ├── detection/
│   │   ├── engine.py        — orchestrates all checkers
│   │   ├── continuity_checker.py
│   │   ├── economic_checker.py
│   │   ├── assembly_checker.py
│   │   ├── sequence_checker.py
│   │   └── anomaly_scorer.py
│   ├── reports/
│   │   ├── report_builder.py
│   │   ├── llm_narrator.py
│   │   └── formatter.py
│   └── api/
│       ├── anomalies.py     — /api/anomalies endpoints
│       ├── reports.py       — /api/reports endpoints
│       ├── objects.py       — /api/objects endpoints
│       ├── stats.py         — /api/stats endpoints
│       └── submit.py        — /api/submit (player tool)
├── frontend/                — React + Tailwind
├── tests/
├── docs/chain-samples/      — raw API/chain response samples
├── explore_chain.py         — chain exploration script
├── pyproject.toml
└── CLAUDE.md
```

## Conventions
- Timestamps: UTC Unix integers always
- Anomaly IDs: `MNL-{YYYYMMDD}-{seq:04d}`
- Report IDs: `MNL-{YYYYMMDD}-{seq:04d}`
- All errors: structured JSON to stderr, never crash
- Idempotent writes: unique constraints prevent double-processing
- Store raw_json always — detection rules may need unanticipated fields

## Hackathon
- EVE Frontier × Sui Hackathon 2026
- Deadline: March 31, 2026
- Solo build, 3-week window
