# The Aegis Stack: Threat Detection and Reputation Infrastructure for EVE Frontier

**A Toolkit for Civilization's Immune System**

*ARETE — March 2026*

---

## Abstract

The hackathon theme is "A toolkit for civilization." Before civilization can coordinate, it needs accountability. EVE Frontier gives players sovereign control over on-chain assets through Smart Assemblies, but sovereignty without security is a liability. When a gate network is exploited, an inventory is drained without a trace, or a reputation system exists only in Discord hearsay, players have no recourse and no record. The Aegis Stack closes this gap with two integrated systems: **Monolith**, a real-time anomaly detection engine with 39 deterministic rules, and **WatchTower**, a behavioral intelligence platform that publishes 6-dimensional reputation scores directly on-chain. Together they form a closed feedback loop — detect threats, verify them against the chain, score the actors, and enforce consequences through Smart Assemblies — all without admin keys, human moderators, or centralized trust.

Both systems are live in production, processing real chain data from Stillness.

---

## 1. The Problem

EVE Frontier's Smart Assembly system is a breakthrough in player sovereignty. Gates, storage units, turrets, and assemblies are fully on-chain objects that players own, configure, and operate. But this sovereignty creates a new class of problems that the game itself doesn't solve:

**No threat detection.** When a gate processes a jump without collecting fuel, when an inventory shifts between snapshots with no transfer event, when an object's version number decreases — nobody knows. These anomalies happen in the space between World API polls, buried in Sui event streams that no player monitors manually.

**No behavioral accountability.** A pilot who ganks new players at gates, hops tribes weekly, and operates suspected alts has no on-chain record of that behavior. Trust is informal — maintained in spreadsheets, Discord channels, and tribal memory that doesn't survive leadership changes.

**No enforcement primitive.** Even if threats were detected and reputations were computed, there's no mechanism to translate that intelligence into Smart Assembly policy. A gate can't deny docking to a known griefer because "known griefer" isn't an on-chain concept.

The Aegis Stack solves all three.

---

## 2. Architecture Overview

The Aegis Stack is a two-layer system with a shared intelligence bus:

```
┌─────────────────────────────────────────────────────────┐
│                    SMART ASSEMBLIES                      │
│         Gates · Storage Units · Turrets · Pods          │
│    ┌──────────────────────────────────────────────┐     │
│    │  "Deny docking if reputation.trust < 40"     │     │
│    │  "Alert if anomaly.severity == CRITICAL"     │     │
│    └──────────────────────────────────────────────┘     │
└────────────────────────┬────────────────────────────────┘
                         │ On-chain queries
         ┌───────────────┴───────────────┐
         │                               │
┌────────▼────────┐            ┌─────────▼────────┐
│   WATCHTOWER    │            │    MONOLITH      │
│  Intelligence   │◄──NEXUS───│   Detection      │
│                 │            │                  │
│ • Fingerprints  │            │ • 39 Rules       │
│ • Reputation    │            │ • 19 Checkers    │
│ • Kill Networks │            │ • Warden (auto-  │
│ • Alt Detection │            │   verification)  │
│ • Dossier NFTs  │            │ • Provenance     │
│ • Oracle Loop   │            │   Chains         │
│ • Story Feed    │            │ • LLM Narration  │
│ • 15 Discord    │            │ • Threat Heatmap │
│   Commands      │            │ • Webhook Alerts │
└────────┬────────┘            └─────────┬────────┘
         │                               │
         └───────────────┬───────────────┘
                         │
              ┌──────────▼──────────┐
              │   SUI BLOCKCHAIN    │
              │   (Stillness)       │
              │                     │
              │  13 Event Types     │
              │  4 Move Modules     │
              │  24,502 Systems     │
              └─────────────────────┘
```

**Monolith** watches the chain for anomalies — events that shouldn't happen, states that don't add up, patterns that indicate exploitation. Every detection carries a cryptographic provenance chain linking it back to specific Sui transactions.

**WatchTower** watches the actors — building behavioral fingerprints, computing trust scores, detecting alts, and publishing reputation on-chain where Smart Assemblies can enforce it.

**NEXUS** is the webhook bus connecting them. Monolith pushes anomaly events to WatchTower. WatchTower enriches entity context back. Third-party builders can subscribe to either.

---

## 3. Monolith: The Detection Engine

### 3.1 Data Ingestion

Monolith subscribes to 13 Sui event types via `suix_queryEvents`, polling every 30 seconds with resumable cursors:

| Event Category | Types |
|----------------|-------|
| Combat | KillmailCreatedEvent |
| Transit | JumpEvent |
| State | StatusChangedEvent |
| Economy | ItemMintedEvent, ItemBurnedEvent, ItemDepositedEvent, ItemWithdrawnEvent, ItemDestroyedEvent |
| Infrastructure | AssemblyCreatedEvent, FuelEvent |
| Identity | CharacterCreatedEvent, OwnerCapTransferred |
| Location | LocationRevealedEvent |

Raw events are stored in a 21-table SQLite database (WAL mode, FTS5 full-text search) and transformed into object state snapshots for delta detection.

### 3.2 Detection Rules (39 Rules, 19 Checkers)

Every rule is deterministic — pure math on chain data, no machine learning, no black-box classifiers. The same input always produces the same output.

**Continuity Rules (C1–C4)** detect impossible state transitions:
- **C1 Ghost Signal** — Unregistered object broadcasting on-chain
- **C2 Lazarus Event** — Destroyed asset resumed transmission
- **C3 Missing Trajectory** — Object jumped states with no flight path
- **C4 Dead Drift** — Assembly stuck in transitional state 10+ minutes

**Economic Rules (E1–E4)** catch conservation violations:
- **E1 Phantom Ledger** — Resources shifted without a paper trail
- **E2 Vanishing Act** — Asset erased between sweeps, no wreckage
- **E3 Double Stamp** — Duplicate mint detected
- **E4 Negative Mass** — Balance went sub-zero

**Assembly Rules (A1–A5)** monitor Smart Assembly integrity:
- **A1 Forked State** — Chain says X, API says Y
- **A2 Toll Runner** — Gate jump without paying fuel
- **A3 Gate Tax Lost** — Fuel burned, traveler never arrived
- **A4 Shadow Inventory** — Cargo shifted without manifest update
- **A5 Silent Seizure** — Ownership changed with no transfer on record

**Sequence Rules (S1–S4)** validate event ordering:
- **S1 Broken Ledger** — Duplicate transaction detected
- **S2 Event Storm** — Suspiciously high event count from single tx
- **S3 Sequence Drift** — Events arrived out of order
- **S4 Blind Spot** — Block processing gap, surveillance dark

**Behavioral Rules** identify player-level patterns:
- **K1/K2** — Duplicate killmails, third-party kill reports
- **CB1/CB2** — Coordinated buying, fleet staging detection
- **BP1** — Automated transaction patterns (bot detection)
- **TH1** — Rapid tribe hopping
- **ES1/ES2** — Orphaned kills, phantom engagements
- **EV1/EV2** — Velocity spikes and market silence

**Infrastructure Rules** track structural threats:
- **OV1/OV2** — State rollbacks, unauthorized modifications
- **WC1** — Wallet resource concentration
- **CC1** — World contract config changes
- **IA1** — Inventory conservation violations
- **DA1** — Derelict assemblies (30+ days dark)
- **OZ1/OZ2** — Orbital zone dark spots, feral AI escalation
- **FA1/FA2** — Hive surges, silent zones
- **P1** — Chain divergence (async Sui GraphQL verification)

### 3.3 Warden: Autonomous Verification

Detected anomalies start as UNVERIFIED. The Warden system autonomously queries the Sui RPC to verify or dismiss each claim:

1. Fetch unverified anomalies (max 10/cycle)
2. Health-check: is the chain reachable?
3. For each anomaly: query on-chain object state (read-only)
4. If the chain confirms the anomaly — VERIFIED
5. If the chain contradicts — DISMISSED
6. Append verification checkpoint to provenance chain

No human in the loop. No write operations. Pure read-only chain verification.

### 3.4 Provenance Chains

Every anomaly carries a provenance chain — an ordered list of evidence entries tracing the detection back to specific Sui transactions:

```
ProvenanceEntry {
    source_type: "chain_event" | "world_state" | "sui_rpc"
    source_id:   tx_digest or snapshot reference
    timestamp:   unix epoch when source data was produced
    derivation:  human-readable explanation
}
```

This is not a summary. It's a verifiable audit trail. Any player can take a Monolith anomaly, follow the provenance chain, and independently confirm it against the Sui explorer.

### 3.5 LLM Narration

Anomalies are narrated in plain English by an LLM intelligence analyst (Anthropic Claude). Each report includes a terse 2-3 sentence summary, investigation steps, and chain references. When the LLM is unavailable, 27 pre-computed template narrations cover all anomaly types — the system never goes silent.

### 3.6 Alerting

Three dispatch channels with configurable severity filters:

- **Discord Webhooks** — CRITICAL and HIGH anomalies, rate-limited, embedded formatting
- **GitHub Issues** — CRITICAL only, auto-filed with chain references and investigation steps, DB-backed deduplication
- **Webhook Subscriptions** — External HTTP endpoints with severity and type filtering

### 3.7 Threat Heatmap

A Canvas2D renderer plots all 24,502 solar systems with anomaly overlays — severity-based coloring, animated event markers, pulsing reticles on active threats, and an interactive stats HUD. 60fps target with drag/pan, pinch zoom, and touch support. The map transforms raw chain data into spatial awareness: where are things going wrong, and how bad is it?

### 3.8 Evaluation Layer

Three measurement scripts validate system quality in CI:

| Script | Measures | CI Gate |
|--------|----------|---------|
| Detection Quality | Precision, recall, F1 per checker vs ground truth | Yes (precision >= 0.85, recall >= 0.70) |
| Narration Quality | Factual grounding, severity alignment, hallucination rate | Informational |
| System Metrics | P50/P95 latency, anomaly rate, cost per report, poll drift | Operational |

The eval layer treats detection quality as a regression-testable property. New rules must not degrade existing precision.

---

## 4. WatchTower: The Intelligence Platform

### 4.1 Behavioral Fingerprints

WatchTower builds a four-dimensional behavioral profile for every entity from on-chain activity:

**Temporal** — When are they active? UTC hour/day distributions, peak activity windows, Shannon entropy scoring for predictability.

**Route** — Where do they go? Gate frequency analysis, system patterns, unique gate/system counts, route entropy.

**Social** — Who do they associate with? Co-transitors, corporate affiliations, solo ratios, top associates.

**Threat** — How dangerous are they? Kill/death ratios, kills-per-day, combat zone analysis, threat level classification.

These fingerprints enable alt detection: comparing two entities' temporal, route, and social patterns produces a similarity score. Same sleep schedule + same gates + same associates = probable alt.

### 4.2 Reputation Scoring (6 Dimensions)

Every entity receives a 0–100 trust score composed of six weighted dimensions:

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| Combat Honor | 25% | Clean kills vs serial ganking |
| Target Diversity | 15% | Range of victims (anti-farming) |
| Reciprocity | 20% | Mutual fights, vendetta participation |
| Consistency | 15% | Behavioral stability over time |
| Community | 15% | Gate construction, positive-sum actions |
| Restraint | 10% | Avoidance of excessive force |

**Rating tiers:** Trusted (80+), Reputable (60–79), Neutral (40–59), Suspicious (20–39), Dangerous (<20)

Scores are deterministic and auditable by design. Same data in = same score out. No appeals process needed because there's no subjective judgment to appeal.

### 4.3 Oracle Loop: Reputation On-Chain

WatchTower doesn't just compute reputation — it publishes it on-chain via Sui Move contracts:

```
Module: watchtower::reputation
Object: OracleCap (admin) → ReputationRegistry (shared)

publish_score(oracle_cap, registry, entity_id, trust_score, dimensions[6])
```

Once on-chain, any Smart Assembly can query it:

```
// Gate access control
if (reputation::get_trust(registry, pilot_id) < 40) {
    deny_docking();
}
```

This closes the loop. Detect behavior, compute reputation, publish to chain, enforce at the assembly level. No Discord DMs, no spreadsheets, no informal trust networks.

### 4.4 Dossier NFTs: Tradeable Intelligence

WatchTower mints intelligence as NFTs — not static images, but live references to shared registries:

| Tier | Price | Content |
|------|-------|---------|
| INTEL | Free | Basic threat data |
| CLASSIFIED | 0.5 SUI | Full behavioral fingerprint |
| ORACLE | 2 SUI | Live-updating intelligence feed |

The key innovation: because Dossier NFTs reference the `ThreatRegistry` (a shared on-chain object), they update automatically as new intelligence comes in. Trading a Dossier NFT doesn't trade a snapshot — it trades a live feed.

### 4.5 Kill Network Analysis

WatchTower constructs directed graphs of combat relationships:
- Attacker-to-victim edges weighted by kill count
- Vendetta detection (mutual kill pairs)
- System clustering (where kills concentrate)
- Force-directed visualization for frontend rendering

### 4.6 Hotzones

Every solar system receives a danger rating based on kill density:

| Level | Threshold | Meaning |
|-------|-----------|---------|
| EXTREME | 50+ kills | Active war zone |
| HIGH | 20–49 | Persistent threat |
| MODERATE | 10–19 | Elevated risk |
| LOW | 3–9 | Occasional conflict |
| MINIMAL | <3 | Quiet space |

Time-windowed (24h, 7d, 30d, all-time) for operational relevance.

### 4.7 Earned Titles

Deterministic titles derived from on-chain statistics — crowd-verifiable, impossible to grant by admin fiat:

- **The Reaper** — 50+ confirmed kills
- **The Marked** — 10+ deaths
- **The Ghost** — 30+ transits with zero combat
- **The Meatgrinder** — 20+ nearby gate kills
- **The Hunter** — Active killer above threshold
- **The Menace** — Unpredictable behavioral patterns

Same data = same title. No appeals needed because there's no subjective judgment.

### 4.8 Story Feed

Auto-generated news items from chain data — engagement clusters, kill streak milestones, new entity appearances, hunter dominance patterns. No human editors. Pure algorithmic event detection pushed via SSE.

### 4.9 Discord Integration (15 Commands)

Full intelligence access without leaving Discord:

`/watchtower` `/killfeed` `/leaderboard` `/feed` `/compare` `/locate` `/history` `/watch` `/unwatch` `/profile` `/opsec` `/nexus` `/dossier` `/help` `/status`

### 4.10 Subscription Tiers

Three tiers with dual payment rails — native SUI on-chain or Stripe fiat:

| Tier | Price | Features |
|------|-------|---------|
| Scout | ~$5/wk | Fingerprints, reputation, leaderboards, story feed |
| Oracle | ~$10/wk | + AI narratives, standing watches, locator agent, SSE alerts |
| Spymaster | ~$20/wk | + Alt detection, kill networks, battle reports, NEXUS webhooks |

Subscriptions are Sui objects (`SubscriptionCap`) minted to the buyer's wallet — portable, verifiable, non-custodial. Early renewal extends from current expiry, not from purchase time.

---

## 5. NEXUS: The Intelligence Bus

NEXUS connects the Aegis Stack components and opens the intelligence layer to third-party builders:

- **HMAC-SHA256 signed payloads** — Recipients can verify authenticity
- **Event filtering** — Subscribe by character, region, event type, severity
- **Tiered quotas** — Scout (no webhooks), Oracle (2 subs, 100/day), Spymaster (10 subs, 1000/day)
- **Retry with exponential backoff** — 3 attempts (1s, 5s, 15s)
- **Circuit breaker** — Pauses after 10 consecutive failures

Any builder can register a webhook and receive anomaly alerts or intelligence updates in real time. The protocol is simple: register a URL, specify your filters, receive signed JSON payloads. NEXUS handles retry, throttling, and delivery guarantees.

---

## 6. The Closed Loop

The Aegis Stack's defining characteristic is that it closes the feedback loop from detection to enforcement:

```
Chain Events → Detection (Monolith) → Verification (Warden)
                                            ↓
Enforcement (Smart Assemblies) ← Reputation (WatchTower Oracle)
                                            ↑
Chain Events → Fingerprinting → Scoring → Publishing
```

Most security tools stop at reporting. Monolith detects anomalies and verifies them against the chain. WatchTower scores the entities involved and publishes those scores on-chain. Smart Assemblies query those scores and enforce access policy. The loop runs continuously — new behavior updates fingerprints, fingerprints update scores, scores update enforcement, enforcement shapes behavior.

This is not a dashboard. It's an immune system.

---

## 7. On-Chain Contracts

Four Sui Move modules deployed to Stillness testnet:

### Reputation Module (`watchtower::reputation`)
- `ReputationRegistry` — shared object storing entity trust scores
- `OracleCap` — admin capability for score publishing
- `publish_score()` — write trust score + 6 dimensions
- `get_trust()` — query trust score (callable by Smart Assemblies)

### Subscription Module (`watchtower::subscription`)
- `SubscriptionRegistry` — tracks tiers, revenue, counts
- `subscribe()` — mint `SubscriptionCap` to wallet
- Overpayment protection (remainder refunded)
- Admin pricing oracle for SUI/USD rate updates

### Titles Module (`watchtower::titles`)
- On-chain earned title records with evidence hashes
- Deterministic — same stats always produce same titles

### Dossier Module (`watchtower::dossier`)
- `ThreatRegistry` — shared intelligence store
- Three NFT tiers (INTEL, CLASSIFIED, ORACLE)
- Live-updating references, not frozen snapshots

---

## 8. What's Live Today

| Metric | Monolith | WatchTower | Combined |
|--------|----------|------------|----------|
| Chain events ingested | 10,774+ | 23,000+ | 33,774+ |
| Detection/analysis rules | 39 | 19 modules | 58 |
| Tests passing | 465 | 774 | 1,239 |
| API endpoints | 21 | 45+ | 66+ |
| Database tables | 21 | 21 | 42 |
| Solar systems mapped | 24,502 | 24,502 | 24,502 |
| Anomalies detected | 304+ | — | 304+ |
| Entities fingerprinted | — | 36,085+ | 36,085+ |
| Killmails analyzed | — | 4,795+ | 4,795+ |
| Sui Move modules | — | 4 | 4 |
| On-chain transactions | — | 68+ | 68+ |
| Discord commands | — | 15 | 15 |
| Dossier NFT tiers | — | 3 | 3 |
| Subscription tiers | — | 3 | 3 |
| Deployment targets | 2 (Fly+Vercel) | 2 (Fly+Vercel) | 4 |

Every number above is from production systems processing real Stillness chain data.

---

## 9. Technical Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11+, FastAPI |
| Frontend | React 19, Vite, Tailwind CSS |
| Database | SQLite WAL + FTS5 (both systems) |
| Chain Integration | Sui JSON-RPC, Sui GraphQL, suix_queryEvents |
| Smart Contracts | Sui Move (4 modules: subscription, reputation, titles, dossier) |
| LLM Integration | Anthropic Claude (narration + narrative generation, with template fallback) |
| Map Rendering | Canvas2D (60fps, 24,502 systems) |
| Alerting | Discord webhooks, GitHub Issues API, HTTP webhook subscriptions |
| Payment | Sui MoveCall (native) + Stripe (fiat) — dual rails |
| Bot | discord.py (15 slash commands with autocomplete) |
| CI/CD | GitHub Actions (ruff, pytest, pip-audit, gitleaks, CodeQL) |
| Hosting | Fly.io (backend) + Vercel (frontend) |
| Testing | pytest, pytest-asyncio, respx (HTTP mocking) |

---

## 10. Design Principles

**Deterministic over probabilistic.** Every detection rule is pure math on chain data. No ML classifiers, no training data dependencies, no unexplainable outputs. The same chain state always produces the same anomalies and the same reputation scores.

**Provenance over assertion.** We don't claim something is wrong — we show the chain evidence and let anyone verify independently. Every anomaly carries its provenance chain. Every reputation score decomposes into six auditable dimensions.

**Enforcement over reporting.** Detection without consequences is just logging. The Oracle Loop publishes reputation on-chain where Smart Assemblies can act on it. This turns intelligence into infrastructure.

**Composable over complete.** The Aegis Stack doesn't try to be everything. It produces primitives — anomaly feeds, trust scores, behavioral fingerprints, webhook events — that other systems can consume. NEXUS is open. The API is public. The contracts are permissionless.

**Operational over theoretical.** Both systems are live. The detection engine runs on a 5-minute cycle. The chain reader polls every 30 seconds. Reputation updates publish to Sui. This is infrastructure that runs, not a specification that could.

---

## 11. Future Work

**Warden Expansion** — Additional verification strategies beyond object-state queries: cross-referencing multiple anomalies, temporal correlation analysis, and consensus verification across Aegis Stack nodes.

**Reputation Delegation** — Allow entities to delegate their reputation to organizational units (tribes, alliances), enabling group-level trust scoring for collective asset management.

**Cross-System Correlation** — Link Monolith anomalies to WatchTower entity profiles automatically: "this anomaly was likely caused by this entity based on temporal and spatial fingerprint overlap."

**Builder SDK** — Package NEXUS subscription, anomaly querying, and reputation lookup into client libraries for Move, TypeScript, and Python.

**Smart Assembly Templates** — Pre-built access control policies that integrate reputation checks: "standard gate" (deny < 40), "high-security storage" (deny < 60), "open relay" (no checks).

---

## 12. Conclusion

The Aegis Stack is the security layer that civilization requires before any other layer can function. Treasuries need threat detection. Governance needs reputation scoring. Trade needs behavioral accountability. Infrastructure needs anomaly alerting.

Monolith tells you what went wrong. WatchTower tells you who did it and whether to trust them. The Oracle Loop makes that intelligence enforceable at the Smart Assembly level. NEXUS opens it all to third-party builders.

Both systems are live. Both are processing real chain data. Both are open for integration.

Civilization needs an immune system. We built it.

---

## Links

| Resource | URL |
|----------|-----|
| Monolith (Live) | https://monolith-evefrontier.vercel.app |
| Monolith API | https://monolith-evefrontier.fly.dev |
| WatchTower (Live) | https://watchtower-evefrontier.vercel.app |
| WatchTower API | https://watchtower-evefrontier.fly.dev |
| Monolith Source | github.com/AreteDriver/monolith |
| WatchTower Source | github.com/AreteDriver/watchtower |

---

## Team

**ARETE** — Solo builder. Both Monolith and WatchTower were live in production, processing real Stillness chain data, before the hackathon was announced. 17 years enterprise operations (IBM, manufacturing, logistics). Now building AI-powered infrastructure for on-chain worlds.
