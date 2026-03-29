# MONOLITH — Build Bible
> Blockchain Anomaly Detector + Structured Bug Report Engine for EVE Frontier
> EVE Frontier × Sui Hackathon 2026 | Deadline: March 31, 2026

---

## What This Is

Monolith is a blockchain integrity monitor for EVE Frontier. It continuously reads
the Sui chain and EVE Frontier World API, detects state anomalies that indicate
bugs or unintended behavior, and generates structured bug reports that CCP and Sui
engineers can act on immediately.

**The core premise:** A blockchain doesn't lie. Every state transition is permanent
and verifiable. If the chain shows something that shouldn't be possible — an item
that vanished without a destruction event, a gate jump that consumed resources but
produced no location change, a smart assembly in a contradictory state — Monolith
finds it, proves it with on-chain evidence, and formats it for triage.

**Two audiences, one tool:**

- **Players** — "Something went wrong with my assets/gate/structure. Monolith gives
  me a formatted bug report with transaction hashes attached. I'm not filing a
  vague ticket — I'm filing proof."

- **CCP + Sui** — "Here are N chain state anomalies detected in the last 24 hours,
  ranked by severity, with full reproduction context and transaction references.
  Your QA team can triage without manual investigation."

**Why this wins the hackathon:**

The hackathon theme is the Sui migration. CCP and Sui's biggest pain point right
now is finding bugs in a live chain migration. A tool that automates that discovery
and formats it for their engineering workflow is directly solving the judges'
problem. Not a tool for players. A tool for the people writing the checks.

---

## The Monolith Name

A monolith records everything. It stands permanent, silent, and unjudgeable.
The blockchain is a monolith — immutable, complete, truthful. Monolith the tool
reads the monolith the chain and speaks what it finds.

It also invokes 2001. A black rectangular object that reveals what humanity
couldn't see on its own. That's the product.

---

## Architecture

### System Diagram

```
EVE Frontier World API (REST)
Sui RPC / MUD Indexer (on-chain events)
Pyrope Explorer (transaction history)
         │
         ▼
┌──────────────────────────────────────────┐
│            INGESTION LAYER               │
│  chain_reader.py   — Sui RPC client      │
│  world_poller.py   — World API REST      │
│  event_stream.py   — MUD event stream    │
│  state_snapshotter.py — periodic state   │
└──────────────────┬───────────────────────┘
                   │ writes raw events
                   ▼
┌──────────────────────────────────────────┐
│         SQLite (WAL + FTS5)              │
│  chain_events       — raw on-chain log   │
│  world_states       — API snapshots      │
│  objects            — tracked entities   │
│  state_transitions  — object history     │
│  anomalies          — detected issues    │
│  bug_reports        — generated reports  │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│          DETECTION ENGINE                │
│  continuity_checker.py  — state gaps     │
│  economic_checker.py    — value leaks    │
│  assembly_checker.py    — contract vs    │
│                           chain state    │
│  sequence_checker.py    — event order    │
│  anomaly_scorer.py      — severity rank  │
└──────────────────┬───────────────────────┘
                   │ writes anomalies
                   ▼
┌──────────────────────────────────────────┐
│          REPORT GENERATOR                │
│  report_builder.py  — structures anomaly │
│  llm_narrator.py    — plain English desc │
│  formatter.py       — CCP/Sui format     │
│  exporter.py        — JSON / Markdown    │
└──────────────────┬───────────────────────┘
                   │ serves
                   ▼
┌──────────────────────────────────────────┐
│         FastAPI REST API                 │
│  /api/anomalies          — list/filter   │
│  /api/anomalies/{id}     — detail        │
│  /api/reports/{id}       — bug report    │
│  /api/reports/generate   — on-demand     │
│  /api/objects/{id}       — entity trail  │
│  /api/health             — system status │
│  /api/stats              — anomaly rates │
└──────────────────┬───────────────────────┘
                   │ serves
                   ▼
┌──────────────────────────────────────────┐
│         React + Tailwind UI              │
│  AnomalyFeed        — live anomaly list  │
│  AnomalyDetail      — full chain trace   │
│  BugReportViewer    — formatted report   │
│  ObjectTracker      — entity state trail │
│  StatsPanel         — anomaly rates      │
│  ReportExporter     — copy/download      │
└──────────────────────────────────────────┘
         │
         ▼
   Discord Webhooks (critical anomaly alerts)
   Anthropic API (plain English narration)
```

### Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Backend | FastAPI + uvicorn | Carries from Frontier Watch, async-native |
| Database | SQLite WAL + FTS5 | Zero infra, handles hackathon scale |
| Chain | Sui RPC + MUD Indexer | Direct chain access, no intermediary |
| Detection | Pure Python | Deterministic rules, easy to audit |
| LLM | Anthropic API | Plain English bug narration, CCP-readable |
| Frontend | React + Tailwind | Carries from Frontier Watch |
| Alerts | Discord webhooks | Critical anomalies → immediate notification |
| Deployment | VPS + persistent SQLite | Single server, hackathon-appropriate |

---

## Core Concept: State Continuity

**This is the engine that makes Monolith work.**

Every object in EVE Frontier has a lifecycle: it is created, it transitions through
states, and it is destroyed. Each transition should have a corresponding on-chain
event. Monolith tracks these lifecycles and flags when the chain shows a transition
without a corresponding event — or an event without a valid preceding state.

### The State Machine Model

```
OBJECT LIFECYCLE (expected):

  [CREATED] → [ACTIVE] → [MODIFIED] → [ACTIVE] → [DESTROYED]
     │              │           │           │           │
  chain event    chain event chain event chain event chain event
  (mint/spawn)  (interaction) (state change) (interaction) (burn/kill)

ANOMALY TYPES:

  Type 1 — STATE GAP:
  [ACTIVE] → [DESTROYED]   (no MODIFIED event, but state changed)
  Object went from A to C. B never happened on chain.

  Type 2 — ORPHAN EVENT:
  [???] → [MODIFIED]       (no CREATED event, object appeared mid-stream)
  Event references object that has no creation record.

  Type 3 — RESURRECTION:
  [DESTROYED] → [ACTIVE]   (object reappeared after destruction record)
  Dead object is doing things. This shouldn't be possible.

  Type 4 — CONTRADICTION:
  Chain says: object X has 500 units
  API says:   object X has 350 units
  Neither was updated. They diverge.

  Type 5 — VALUE LEAK:
  ISK/items entering or leaving the system without corresponding events.
  Sum of all creation events ≠ sum of all destruction events + current supply.

  Type 6 — SEQUENCE VIOLATION:
  Event B depends on Event A. B timestamp < A timestamp.
  The effect happened before the cause.
```

---

## Detection Engine — Detailed Rules

### Detector 1: Continuity Checker
**File:** `detection/continuity_checker.py`
**Runs:** Every 5 minutes on new events

Rules:
```
RULE C1 — Missing creation record
  IF object_id appears in any event
  AND object_id NOT IN objects table
  THEN anomaly: ORPHAN_OBJECT, severity: MEDIUM

RULE C2 — Post-destruction activity  
  IF object_id has destruction_event in state_transitions
  AND subsequent events reference object_id after destruction_timestamp
  THEN anomaly: RESURRECTION, severity: CRITICAL

RULE C3 — State jump without transition
  IF object state at T1 = STATE_A
  AND object state at T2 = STATE_C (T2 > T1)
  AND no STATE_B transition event exists between T1 and T2
  AND STATE_A → STATE_C is not a valid direct transition
  THEN anomaly: STATE_GAP, severity: HIGH

RULE C4 — Unresolved pending state
  IF object entered PENDING state > 10 minutes ago
  AND no resolution event exists
  THEN anomaly: STUCK_OBJECT, severity: MEDIUM
```

### Detector 2: Economic Checker
**File:** `detection/economic_checker.py`
**Runs:** Every 15 minutes on full supply snapshot

Rules:
```
RULE E1 — Item supply leak
  IF sum(creation_events.quantity) - sum(destruction_events.quantity)
     ≠ current_supply (within tolerance)
  THEN anomaly: SUPPLY_DISCREPANCY, severity: HIGH
  evidence: { expected_supply, actual_supply, delta, calculation_window }

RULE E2 — Zero-cost destruction
  IF item destroyed (burn event)
  AND no corresponding combat/salvage/dismantle event
  AND quantity > threshold
  THEN anomaly: UNEXPLAINED_DESTRUCTION, severity: HIGH

RULE E3 — Duplicate creation
  IF creation_event_id appears more than once in chain
  THEN anomaly: DUPLICATE_MINT, severity: CRITICAL
  (This is a serious Sui migration bug vector)

RULE E4 — Negative balance
  IF any tracked balance goes negative at any point in history
  THEN anomaly: NEGATIVE_BALANCE, severity: CRITICAL
```

### Detector 3: Smart Assembly Checker
**File:** `detection/assembly_checker.py`
**Runs:** Every 5 minutes on assembly state changes

Rules:
```
RULE A1 — Contract vs chain state mismatch
  IF smart_assembly.contract_state ≠ world_api.assembly_state
  AND last_sync_attempt < 2 minutes ago
  THEN anomaly: CONTRACT_STATE_MISMATCH, severity: HIGH
  evidence: { contract_state, api_state, assembly_id, last_known_good }

RULE A2 — Gate jump without fuel consumption
  IF gate_jump_event recorded
  AND fuel_consumption_event NOT recorded within 30 seconds
  THEN anomaly: FREE_GATE_JUMP, severity: HIGH
  (Potential exploit vector — flag immediately)

RULE A3 — Gate jump with fuel but no position change
  IF fuel_consumption_event recorded for gate
  AND character position unchanged after 60 seconds
  THEN anomaly: FAILED_GATE_TRANSPORT, severity: MEDIUM
  (Player lost fuel, didn't move — reimbursement candidate)

RULE A4 — Storage unit phantom items
  IF storage_snapshot_T1.items ≠ storage_snapshot_T2.items
  AND no add/remove events between T1 and T2
  THEN anomaly: PHANTOM_ITEM_CHANGE, severity: HIGH

RULE A5 — Ownership without transfer event
  IF current_owner ≠ last_known_owner
  AND no ownership_transfer event between snapshots
  THEN anomaly: UNEXPLAINED_OWNERSHIP_CHANGE, severity: CRITICAL
```

### Detector 4: Sequence Checker
**File:** `detection/sequence_checker.py`
**Runs:** Continuous on new event ingestion

Rules:
```
RULE S1 — Effect before cause
  IF event_B.depends_on = event_A.id
  AND event_B.timestamp < event_A.timestamp
  THEN anomaly: TEMPORAL_VIOLATION, severity: CRITICAL
  (Fundamental chain integrity issue)

RULE S2 — Duplicate transaction
  IF transaction_hash appears more than once
  THEN anomaly: DUPLICATE_TRANSACTION, severity: CRITICAL

RULE S3 — Missing prerequisite
  IF event requires prerequisite_event
  AND prerequisite_event NOT found in chain history
  THEN anomaly: MISSING_PREREQUISITE, severity: HIGH

RULE S4 — Out-of-order block processing
  IF event processed from block N
  AND previous event from block N+5 already processed
  AND gap > threshold
  THEN anomaly: BLOCK_PROCESSING_GAP, severity: MEDIUM
  (May indicate indexer issue, not chain issue)
```

### Anomaly Scoring
**File:** `detection/anomaly_scorer.py`

```python
SEVERITY_WEIGHTS = {
    "CRITICAL": 100,   # Data integrity broken, possible exploit
    "HIGH": 60,        # Significant bug, player impact likely
    "MEDIUM": 30,      # Behavioral anomaly, investigate
    "LOW": 10,         # Unusual pattern, log for review
}

ANOMALY_CATEGORIES = {
    "EXPLOIT_VECTOR": CRITICAL,    # Free resources, duplication
    "DATA_INTEGRITY": CRITICAL,    # Chain state corrupted
    "PLAYER_LOSS": HIGH,           # Player lost assets due to bug
    "STATE_INCONSISTENCY": HIGH,   # System in wrong state
    "BEHAVIORAL": MEDIUM,          # Unexpected but not breaking
    "PERFORMANCE": LOW,            # Slow resolution, minor gaps
}
```

---

## Bug Report Format

This is what Monolith outputs. Designed to be immediately actionable by a
CCP or Sui engineer with zero additional investigation required.

### Report Schema

```
MONOLITH BUG REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Report ID:     MNL-2026-03-15-0047
Generated:     2026-03-15T14:32:11Z
Severity:      HIGH
Category:      STATE_INCONSISTENCY
Detector:      assembly_checker / RULE A4
Status:        UNVERIFIED

SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Storage unit [SSU-0x4f2a...] in system [Uphenapad] showed item count
change of -47 units between snapshot T1 and T2 with no corresponding
add/remove events on chain during the observation window.

AFFECTED ENTITIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Object Type:   Smart Storage Unit
Object ID:     0x4f2a8c91d3e7b5f2a8c91d3e7b5f2a8c
Owner Corp:    [corp_id]
System:        Uphenapad (system_id: 30004759)
Discovery:     2026-03-15T14:28:44Z

EVIDENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Snapshot T1:
  Timestamp:   2026-03-15T14:00:00Z
  Item Count:  347
  Hash:        0x9a2b...

Snapshot T2:
  Timestamp:   2026-03-15T14:15:00Z
  Item Count:  300
  Hash:        0x7c4d...

Chain Events (T1 → T2 window):
  [NONE FOUND]

Expected Events:
  storage_item_remove OR storage_item_transfer

Delta:
  -47 units with no on-chain explanation

CHAIN REFERENCES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Block range:   [block_T1] → [block_T2]
Explorer:      https://explorer.sui.io/...
Pyrope:        https://pyrope.nursery.reitnorf.com/...

REPRODUCTION CONTEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Observation window: 15 minutes
Snapshot interval:  15 minutes
Detection rule:     RULE A4 — Storage unit phantom items
First occurrence:   This report
Recurrence:         N/A (first detection)

RECOMMENDED INVESTIGATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Query chain directly for all events referencing object
   0x4f2a8c91d3e7b5f2a8c91d3e7b5f2a8c between T1 and T2
2. Check if MUD Indexer missed events (indexer gap vs chain gap)
3. Verify storage contract state matches World API state
4. If confirmed: item deletion without event is a contract bug

PLAIN ENGLISH (LLM)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A storage unit in Uphenapad lost 47 items between 14:00 and 14:15 UTC
with nothing recorded on chain to explain it. Either the items were
removed through a code path that doesn't emit events, or the MUD indexer
missed those events. The first scenario is a contract bug — items should
never move without an on-chain record. The second is an indexer bug.
Either way this is worth investigating before launch.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generated by MONOLITH v0.1.0
EVE Frontier Blockchain Integrity Monitor
https://github.com/AreteDriver/monolith
```

---

## Feature Breakdown

### Feature 1: Live Anomaly Feed
The home screen. Real-time stream of detected anomalies as they're found.

What it shows:
- Anomaly type, severity badge (CRITICAL/HIGH/MEDIUM/LOW)
- Affected entity (object ID, type, system)
- Detection time
- One-line description
- "View Report" button → full bug report

Auto-refreshes every 30 seconds. CRITICAL anomalies push to Discord immediately.

Color coding:
- CRITICAL: red pulse animation
- HIGH: orange
- MEDIUM: yellow
- LOW: grey

### Feature 2: Anomaly Detail + Chain Trace
Full forensic view of a single anomaly.

What it shows:
- Complete evidence block (snapshots, events, delta)
- Chain transaction links (Pyrope Explorer, Sui Explorer)
- Timeline of all events for this object
- State transition diagram (visual — object lifecycle with the gap highlighted)
- Related anomalies (same object, same system, same time window)
- Generate Bug Report button

### Feature 3: Object State Tracker
Track any object's full chain history.

Input: Object ID (smart assembly, character, item)
Output:
- Complete state transition timeline
- Every on-chain event referencing this object
- Current state vs last known good state
- Any anomalies detected for this object
- Owner history

This is the player-facing tool. "My gate isn't working" → paste gate ID →
see exactly what the chain says happened to it.

### Feature 4: Bug Report Generator
Transforms a raw anomaly into a formatted, actionable bug report.

Two modes:
1. **Auto-generate** — Monolith detects anomaly, generates report immediately
2. **Player-submit** — Player pastes object ID + describes what they observed →
   Monolith pulls chain state, attaches evidence, generates formatted report

Output formats:
- Markdown (for GitHub Issues / CCP bug tracker)
- JSON (for API submission)
- Plain text (for Discord/forum posting)

LLM layer: Anthropic API writes the "Plain English" summary section.
Engineers shouldn't have to decode raw chain data to understand the bug.

### Feature 5: Statistical Dashboard
Server-wide anomaly health at a glance.

What it shows:
- Anomaly rate over time (chart — how many per hour)
- Breakdown by type (pie/bar)
- Breakdown by severity
- Most affected systems (heatmap)
- Most affected object types
- Detection rule hit rates (which rules are firing most)
- False positive rate (if manually marked)

This is the CCP/Sui exec view. "Is the Sui migration stable?" →
look at anomaly rate trend. Declining = good. Spiking = investigate.

### Feature 6: Discord Alert Integration
Critical anomalies need immediate attention.

Alert tiers:
- CRITICAL → fires immediately, pings @here in configured channel
- HIGH → fires within 5 minutes, no ping
- MEDIUM/LOW → daily digest summary only

Discord embed format:
```
🚨 MONOLITH CRITICAL ALERT
Type: DUPLICATE_MINT
Object: [item_type] x[quantity]
System: [system_name]
Time: [timestamp]
Report: https://monolith.app/reports/MNL-xxx
Tx Hash: 0x...
```

---

## Database Schema

```sql
-- Raw chain events as they arrive
CREATE TABLE chain_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE,
    event_type TEXT,
    object_id TEXT,
    object_type TEXT,
    system_id TEXT,
    block_number INTEGER,
    transaction_hash TEXT,
    timestamp INTEGER,
    raw_json TEXT,
    processed INTEGER DEFAULT 0
);

-- World API state snapshots
CREATE TABLE world_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id TEXT,
    object_type TEXT,
    state_data TEXT,  -- JSON
    snapshot_time INTEGER,
    source TEXT       -- 'world_api' or 'chain'
);

-- Tracked objects and their current known state
CREATE TABLE objects (
    object_id TEXT PRIMARY KEY,
    object_type TEXT,
    created_at INTEGER,
    destroyed_at INTEGER,
    current_state TEXT,
    current_owner TEXT,
    system_id TEXT,
    last_event_id TEXT,
    last_seen INTEGER,
    anomaly_count INTEGER DEFAULT 0
);

-- Full state transition history per object
CREATE TABLE state_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id TEXT,
    from_state TEXT,
    to_state TEXT,
    event_id TEXT,
    transaction_hash TEXT,
    block_number INTEGER,
    timestamp INTEGER,
    is_valid INTEGER DEFAULT 1,  -- set 0 if anomalous
    FOREIGN KEY (object_id) REFERENCES objects(object_id)
);

-- Detected anomalies
CREATE TABLE anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anomaly_id TEXT UNIQUE,  -- MNL-{date}-{seq}
    anomaly_type TEXT,
    severity TEXT,           -- CRITICAL/HIGH/MEDIUM/LOW
    category TEXT,
    detector TEXT,           -- which rule fired
    rule_id TEXT,
    object_id TEXT,
    system_id TEXT,
    detected_at INTEGER,
    evidence_json TEXT,      -- full evidence block
    status TEXT DEFAULT 'UNVERIFIED',  -- UNVERIFIED/CONFIRMED/FALSE_POSITIVE/RESOLVED
    report_id TEXT,
    discord_alerted INTEGER DEFAULT 0
);

-- Generated bug reports
CREATE TABLE bug_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id TEXT UNIQUE,   -- MNL-{date}-{seq}
    anomaly_id TEXT,
    title TEXT,
    severity TEXT,
    category TEXT,
    summary TEXT,
    evidence_json TEXT,
    plain_english TEXT,      -- LLM-generated
    chain_references TEXT,   -- JSON array of tx hashes
    reproduction_context TEXT,
    recommended_investigation TEXT,
    generated_at INTEGER,
    format_markdown TEXT,    -- pre-rendered markdown
    format_json TEXT,        -- pre-rendered JSON
    FOREIGN KEY (anomaly_id) REFERENCES anomalies(anomaly_id)
);

-- FTS5 for searching reports and anomalies
CREATE VIRTUAL TABLE anomalies_fts USING fts5(
    anomaly_type, object_id, system_id, evidence_json,
    content=anomalies
);
```

---

## Claude Code Session Prompts

### Prompt 1: Project Initialization

```
You are building Monolith — a blockchain integrity monitor and bug report
generator for EVE Frontier on Sui.

Monolith reads on-chain events and World API state, detects anomalies where
the chain shows something that shouldn't be possible, and generates structured
bug reports for CCP and Sui engineers.

Tech stack:
- Backend: FastAPI + uvicorn, Python 3.11+
- Database: SQLite with FTS5 and WAL mode
- Chain: Sui RPC + EVE Frontier World API REST
- Detection: Pure Python rule engine
- LLM: Anthropic API (claude-sonnet-4-5) for plain English narration
- Frontend: React + Tailwind
- Alerts: Discord webhooks

CLAUDE.md is at root — read it before any work.

Architecture principles:
- Detection rules are pure functions: (events, states) → anomaly | None
- Never mutate source data — anomalies table is append-only
- Evidence is self-contained in the anomaly record — no joins needed to render a report
- Severity is deterministic from rule — no LLM in the detection path
- LLM is only used for plain English narration AFTER detection
- False positive rate matters — rules must have low noise

Current task: Initialize project structure.
1. backend/main.py — FastAPI app, health endpoint, CORS
2. backend/db/database.py — SQLite setup, WAL mode, all CREATE TABLE statements
3. backend/ingestion/chain_reader.py — Sui RPC client skeleton
4. backend/ingestion/world_poller.py — World API polling skeleton
5. backend/detection/__init__.py — detection engine base class
6. backend/reports/report_builder.py — report schema and builder skeleton
7. frontend/ — React shell with dark theme
8. CLAUDE.md — project context

Skeleton only. No business logic yet.
```

### Prompt 2: Ingestion Layer

```
You are working on Monolith. Read CLAUDE.md first.

Build the data ingestion layer — everything that reads from chain and API.

Sources:
1. EVE Frontier World API: https://blockchain-gateway-nova.nursery.reitnorf.com
   - Poll /smartassemblies, /characters, /solarsystems, /types
   - Snapshot storage unit states every 15 minutes
   - Snapshot character positions every 5 minutes (if available)
   - Write to world_states table

2. Sui RPC / MUD Indexer (confirm URL from sandbox exploration):
   - Subscribe to all events for Frontier's contract addresses
   - On each event: normalize, write to chain_events table
   - Maintain block_number cursor — never process same block twice
   - On startup: backfill last 24 hours if database is empty

3. state_snapshotter.py:
   - Every 5 minutes: compare latest world_state to previous snapshot
   - Write delta to state_transitions table
   - Flag objects where API state diverges from last known chain state

Principles:
- Never crash. All errors logged as structured JSON to stderr.
- Idempotent writes — unique constraints prevent double-processing
- Store raw_json always — detection rules may need fields we didn't anticipate
- Timestamps always UTC Unix integers — no timezone hell

Write an explore_chain.py script that:
- Hits all World API endpoints
- Attempts Sui RPC connection
- Prints all discovered event types and field names
- Saves samples to docs/chain-samples/
Run this first before building the main ingestion loop.
```

### Prompt 3: Detection Engine

```
You are working on Monolith. Read CLAUDE.md first.

Build the detection engine — the core of the product.

Detection runs as a background task every 5 minutes on new events.
Rules are pure functions. No side effects. Input: events + states. Output: anomaly dict or None.

Implement these files:

1. detection/continuity_checker.py
   Rules: C1 (orphan object), C2 (resurrection), C3 (state gap), C4 (stuck object)
   
2. detection/economic_checker.py
   Rules: E1 (supply discrepancy), E2 (unexplained destruction), 
          E3 (duplicate mint), E4 (negative balance)

3. detection/assembly_checker.py
   Rules: A1 (contract vs API mismatch), A2 (free gate jump),
          A3 (failed gate transport), A4 (phantom item change),
          A5 (unexplained ownership change)

4. detection/sequence_checker.py
   Rules: S1 (temporal violation), S2 (duplicate transaction),
          S3 (missing prerequisite), S4 (block processing gap)

5. detection/anomaly_scorer.py
   Assigns severity and category based on rule type.
   Returns structured anomaly dict with all evidence inline.

6. detection/engine.py
   - Orchestrates all checkers
   - Runs every 5 minutes via FastAPI background task
   - Writes confirmed anomalies to anomalies table
   - Triggers Discord alert for CRITICAL/HIGH immediately

Anomaly dict structure:
{
  "anomaly_id": "MNL-{YYYYMMDD}-{seq:04d}",
  "anomaly_type": "PHANTOM_ITEM_CHANGE",
  "severity": "HIGH",
  "category": "STATE_INCONSISTENCY",
  "detector": "assembly_checker",
  "rule_id": "A4",
  "object_id": "...",
  "system_id": "...",
  "detected_at": unix_timestamp,
  "evidence": {
    "snapshot_t1": {...},
    "snapshot_t2": {...},
    "events_in_window": [...],
    "delta": {...}
  }
}

Rules must be conservative — prefer false negatives over false positives.
If uncertain, emit LOW severity not CRITICAL.
Each rule must have a docstring explaining exactly what it detects and why it matters.
```

### Prompt 4: Report Generator + LLM Narration

```
You are working on Monolith. Read CLAUDE.md first.

Build the bug report generator — transforms anomalies into structured, 
actionable reports for CCP and Sui engineers.

1. reports/report_builder.py
   - Takes anomaly dict
   - Builds complete report structure (see CLAUDE.md for format)
   - Populates all sections from evidence inline in the anomaly
   - Generates Report ID: MNL-{YYYYMMDD}-{seq:04d}
   - Renders to: markdown string, JSON dict, plain text
   - Stores all three formats in bug_reports table

2. reports/llm_narrator.py
   - Called after report_builder, before final storage
   - Sends structured evidence to Anthropic API
   - Prompt:

SYSTEM: You are a blockchain engineer's assistant. You receive structured
anomaly data from an EVE Frontier chain monitor and write plain English
explanations for the "Plain English" section of bug reports. Your audience
is a CCP or Sui engineer. Be precise, factual, and concise. Max 100 words.
Explain what happened, why it's a problem, and what it likely indicates.
Do not speculate beyond what the evidence supports.

USER: [anomaly_type, evidence_json, rule_id, severity]

   - Caches result — never re-call LLM for same anomaly_id
   - Falls back to template text if API unavailable

3. reports/formatter.py
   - Renders the full report template (see CLAUDE.md for exact format)
   - Markdown version uses proper headers and code blocks
   - JSON version is machine-readable for API submission
   - Plain text version strips all formatting

4. GET /api/reports/{report_id} — returns report in requested format
   ?format=markdown|json|text (default: markdown)
5. POST /api/reports/generate — accepts anomaly_id, generates report on demand
6. GET /api/reports — list reports, filterable by severity/date/status
```

### Prompt 5: Frontend — Anomaly Feed + Detail

```
You are working on Monolith. Read CLAUDE.md first.

Build the frontend — dark, precise, forensic aesthetic.
Think: terminal meets incident response dashboard. Not a game UI.

1. AnomalyFeed component (home page):
   - Polls GET /api/anomalies every 30s
   - Scrolling list, newest first
   - Each row: severity badge | anomaly_type | object_id (truncated) | system | time ago
   - Severity colors: CRITICAL=red pulse | HIGH=orange | MEDIUM=yellow | LOW=grey
   - Click row → AnomalyDetail
   - Filter bar: severity checkboxes, type dropdown, system search
   - CRITICAL anomalies get a subtle red border + pulse animation

2. AnomalyDetail page (/anomalies/{id}):
   - Full evidence block in monospace code style
   - Chain reference links (external → Pyrope Explorer)
   - State transition timeline: visual diagram showing object lifecycle
     with the anomalous gap highlighted in red
   - Related anomalies (same object or system, last 24h)
   - "Generate Bug Report" button → POST /api/reports/generate

3. BugReportViewer page (/reports/{id}):
   - Renders the full formatted report
   - Top: severity badge, report ID, generated timestamp
   - Sections as the template defines
   - "Copy Markdown" button (copies format_markdown to clipboard)
   - "Download JSON" button
   - "Copy Plain Text" button
   - Status badge: UNVERIFIED / CONFIRMED / FALSE_POSITIVE / RESOLVED
   - Status update dropdown (for CCP internal use)

4. ObjectTracker page (/objects/{id}):
   - Input: paste any object ID
   - Timeline: vertical list of all state transitions, newest first
   - Each transition: from_state → to_state | event_id | tx_hash | timestamp
   - Anomalous transitions highlighted red
   - "View on Pyrope" link for each transaction

Style principles:
- Black background (#0a0a0a)
- Monospace font for IDs, hashes, data
- Sans-serif for prose
- Amber (#f59e0b) for primary accent
- Red (#ef4444) for CRITICAL
- No rounded corners on data elements — sharp, precise
- No gradients — flat, functional
```

### Prompt 6: Statistical Dashboard + Discord Alerts

```
You are working on Monolith. Read CLAUDE.md first.

Build the stats dashboard and Discord alert system.

Stats Dashboard (/stats):

Backend:
1. GET /api/stats — returns:
   {
     anomaly_rate_24h: N,          // total anomalies last 24h
     anomaly_rate_by_hour: [...],  // last 24 buckets
     by_severity: { CRITICAL: N, HIGH: N, ... },
     by_type: { PHANTOM_ITEM_CHANGE: N, ... },
     by_system: [ { system_id, name, count } ],  // top 10
     by_detector: { assembly_checker: N, ... },
     false_positive_rate: 0.0N,
     uptime_seconds: N,
     last_block_processed: N,
     events_processed_24h: N
   }

Frontend:
1. StatsPanel page:
   - Top row: 4 stat cards (anomalies 24h, CRITICAL count, events processed, uptime)
   - Anomaly rate chart: recharts AreaChart, last 24h by hour
   - Severity breakdown: recharts PieChart
   - Type breakdown: recharts HorizontalBarChart (top 10 types)
   - System heatmap: table sorted by anomaly count
   - Detector hit rates: which rules are firing

Discord Alerts:
2. notifier.py (upgrade from skeleton):
   - CRITICAL: fire immediately on detection
     Embed color: 15158332 (red)
     Title: "🚨 MONOLITH CRITICAL — {anomaly_type}"
     Fields: Object | System | Time | Report Link | Tx Hash
     Ping: @here

   - HIGH: fire within 5 minutes (batch if multiple)
     Embed color: 15105570 (orange)
     Title: "⚠️ MONOLITH HIGH — {anomaly_type}"
     No ping

   - Daily digest (MEDIUM/LOW): 
     Fires at 00:00 UTC
     Lists counts by severity and type for past 24h
     Links to /stats

   Rate limit: max 5 Discord messages per minute
   Dedup: same anomaly_id never fires twice
```

### Prompt 7: Player Bug Submission Tool

```
You are working on Monolith. Read CLAUDE.md first.

Build the player-facing bug submission tool — the self-service interface
for players to report bugs backed by chain evidence.

This is different from the automated detection. Players observed something
wrong. They tell Monolith what they saw. Monolith pulls the chain state,
attaches evidence, and generates a formatted report they can submit.

Backend:
1. POST /api/submit — player submits observation:
   {
     object_id: "0x...",          // the thing that broke
     object_type: "gate|storage|character|item",
     observed_at: unix_timestamp, // when they noticed it
     description: "string",       // what they saw happen
     character_name: "string"     // optional
   }

2. Handler:
   - Fetch all chain events for object_id in ±30 min window around observed_at
   - Fetch world_states snapshots for same window
   - Run all detectors against this specific object + window
   - If anomaly found: attach to submission, generate full report
   - If no anomaly found: generate "No anomaly detected" report with raw
     chain data attached (still useful — may be an indexer miss)
   - Return report_id

3. GET /api/submit/{submission_id} — poll for result (async generation)

Frontend:
1. SubmitPage (/submit):
   - Clean form: object ID field | object type selector | datetime picker | 
     description textarea | character name (optional)
   - Paste helper: detect object ID format from clipboard
   - "Find Evidence" button → POST, show loading spinner
   - Result: either full BugReportViewer embed OR "no anomaly detected"
     card with raw chain data and option to still export

2. If no anomaly detected, show:
   "Monolith did not detect a rule violation, but here is the raw chain
   state for your object during the reported window. This may indicate
   an event the indexer missed. Include this data in your manual report."
   [raw chain events in copyable code block]

3. Share button: generates shareable URL for the report
   Anyone with the URL can view it without auth.
```

---

## Build Order / Sprints

### Sprint 1: Foundation + Exploration (Days 1–4)
**Goal:** Chain data flowing, schema live, can see raw events

- [ ] Project scaffold (FastAPI, SQLite, React shell)
- [ ] explore_chain.py — discover all event types and field names
- [ ] Database schema — all CREATE TABLE statements with real field names
- [ ] world_poller.py — polling loop, writes to world_states
- [ ] chain_reader.py — Sui/MUD connection, writes to chain_events
- [ ] state_snapshotter.py — delta tracking between snapshots
- [ ] Health endpoint — uptime + row counts + last block processed

**Done when:** chain_events table has real data, world_states has snapshots.

### Sprint 2: Detection Engine (Days 5–10)
**Goal:** Anomalies being detected and stored

- [ ] continuity_checker.py — C1-C4 rules
- [ ] economic_checker.py — E1-E4 rules
- [ ] assembly_checker.py — A1-A5 rules
- [ ] sequence_checker.py — S1-S4 rules
- [ ] anomaly_scorer.py — severity assignment
- [ ] detection/engine.py — orchestration + background task
- [ ] Verify rules fire against known-bad test fixtures

**Done when:** anomalies table has entries, detection log shows rule hits.

### Sprint 3: Report Generator + LLM (Days 11–16)
**Goal:** Full formatted bug reports generating automatically

- [ ] report_builder.py — full report structure
- [ ] llm_narrator.py — Anthropic API integration
- [ ] formatter.py — markdown / JSON / text renders
- [ ] GET/POST /api/reports endpoints
- [ ] Discord notifier — CRITICAL alerts firing
- [ ] BugReportViewer frontend component

**Done when:** Can view a complete formatted bug report in browser and copy markdown.

### Sprint 4: Frontend + Player Tool (Days 17–22)
**Goal:** Full UI live, player submission working

- [ ] AnomalyFeed — live, filtered, severity-colored
- [ ] AnomalyDetail — chain trace + state diagram
- [ ] ObjectTracker — any object ID → full history
- [ ] SubmitPage — player self-service
- [ ] StatsPanel — server-wide anomaly health
- [ ] Discord alert testing end-to-end

**Done when:** Full demo flow: detection → report → Discord alert → player view.

### Sprint 5: Polish + Hackathon Submission (Days 23–31)
**Goal:** Judges can run it, understand it, trust it

- [ ] Landing page explaining what Monolith is and why it matters
- [ ] README with setup instructions
- [ ] Demo script — walkthrough of a real detected anomaly
- [ ] False positive audit — manually review all anomalies, mark status
- [ ] Performance check — detection engine under 30s per cycle
- [ ] Deploy to VPS with persistent SQLite
- [ ] Hackathon submission writeup

**Done when:** Complete demo recorded. Judges can run `docker-compose up` and see live anomalies.

---

## Hackathon Positioning

**The pitch to judges:**

"The Sui migration is the hardest thing CCP has done technically. Moving a live
game's economy to a new chain while players are still playing is an enormous
engineering challenge. Monolith is a QA tool for that migration. It reads the
chain continuously, detects state anomalies that indicate bugs, and generates
structured reports that CCP and Sui engineers can act on immediately. Every bug
Monolith finds before launch is a player who doesn't lose their assets to a
contract error."

**Why this wins:**
- Directly serves the hackathon's stated theme (Sui migration)
- Solves CCP's actual engineering problem, not a player convenience
- The output (structured bug reports with chain evidence) is immediately useful
- No other submission will be doing automated chain integrity monitoring
- Demonstrates deep understanding of what a chain migration actually risks

**Demo flow for judges:**
1. Show live anomaly feed — real anomalies detected in Frontier's chain
2. Click one → full evidence block with chain references
3. Click Generate Report → formatted bug report with LLM plain English
4. Show stats dashboard — anomaly rate trend, breakdown by type
5. Show player submission tool — paste a gate ID, get chain state back

**The closing line:**
"Monolith doesn't just find bugs. It makes them impossible to ignore."

---

## Key Design Decisions

**Why rules-based not ML:** Detection rules must be auditable. If Monolith says
a gate jump was free, CCP needs to understand exactly why. A ML model that says
"this looks anomalous" is not useful. A rule that says "fuel_consumption_event
was not recorded within 30 seconds of gate_jump_event, transaction hashes X and Y"
is actionable.

**Why LLM only in narration:** LLMs are not reliable for binary anomaly detection.
They hallucinate. A rule that fires incorrectly is a false positive — annoying but
auditable. An LLM that invents a bug that doesn't exist undermines trust in the
entire tool. LLM is used only to translate confirmed anomalies into plain English.

**Why SQLite not Postgres:** Three weeks. Solo build. SQLite WAL handles the
write patterns fine. The detection engine reads from chain_events, writes to
anomalies — that's two tables with straightforward access patterns. Postgres
is unnecessary complexity for the hackathon window.

**Why evidence is self-contained:** Every anomaly record contains its full evidence
inline as JSON. No joins needed to render a report. This means reports are portable
— export one anomaly record and you have everything needed to reproduce the bug.

**Why player submission matters:** Automated detection has coverage limits. Players
will encounter bugs Monolith's rules don't catch. The player submission tool extends
Monolith's coverage to human observation while maintaining the chain-evidence standard.
A player report without evidence is noise. A player report with attached chain state
is signal.
