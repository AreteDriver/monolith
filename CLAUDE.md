# Monolith — Blockchain Anomaly Detector for EVE Frontier

## What This Is
Blockchain integrity monitor for EVE Frontier on Sui. Reads on-chain events and World API state, detects anomalies, generates structured bug reports for CCP/Sui engineers.

## Tech Stack
- **Backend**: FastAPI + uvicorn, Python 3.11+
- **Database**: SQLite WAL + FTS5
- **Chain**: Sui RPC + EVE Frontier World API REST
- **Detection**: Pure Python rule engine (deterministic, auditable)
- **LLM**: Anthropic API (claude-sonnet-4-5) — narration ONLY, never detection
- **Frontend**: React + Tailwind
- **Alerts**: Discord webhooks

## Architecture Principles
- Detection rules are pure functions: `(events, states) → anomaly | None`
- Never mutate source data — anomalies table is append-only
- Evidence is self-contained in the anomaly record — no joins needed to render a report
- Severity is deterministic from rule — no LLM in the detection path
- LLM is only used for plain English narration AFTER detection
- False positive rate matters — rules must have low noise
- Prefer false negatives over false positives

## Key URLs
- World API: `https://blockchain-gateway-nova.nursery.reitnorf.com`
- Pyrope Explorer: `https://pyrope.nursery.reitnorf.com`
- Sui Explorer: `https://suiscan.xyz`

## Project Structure
```
monolith/
├── backend/
│   ├── main.py              — FastAPI app entry
│   ├── config.py            — Settings (env vars)
│   ├── db/
│   │   └── database.py      — SQLite setup, schema, WAL
│   ├── ingestion/
│   │   ├── chain_reader.py  — Sui RPC client
│   │   ├── world_poller.py  — World API REST polling
│   │   ├── event_stream.py  — MUD event stream
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
