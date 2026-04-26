# Aegis Stack Rework Spec

> **Purpose:** Decouple the Aegis Stack components from their EVE Frontier origin, extract Monolith as the general-purpose anomaly detection primitive (P4), and reposition Frontier Watch as a reusable dashboard template. aicards.fun becomes the Attestation primitive reference implementation.

---

## Part 1: Strategy

### 1.1 Current state

The Aegis Stack was submitted to the DeepSurge × EVE Frontier × Sui Hackathon 2026 ($80K prize pool) and scored ~9.4/10 internally. It consists of:

- **Frontier Watch** — live operational intel dashboard at watchtower-evefrontier.vercel.app
- **Monolith** — blockchain anomaly detector, 31 detection rules, 1,034 tests
- **aicards.fun** — NFT card gacha on Sui

IP licensing was confirmed non-exclusive, which is the critical detail. You retain the ability to reuse the components commercially outside the hackathon context.

### 1.2 The diagnosis

The Aegis Stack is a well-executed portfolio piece that is buried under its own framing. "EVE Frontier hackathon submission" is a credential — fine on a resume, fine on LinkedIn. But the components are generally valuable and the hackathon framing limits them.

Three specific problems:

**Monolith is hidden.** 1,034 tests and 31 production rules is substantial engineering work. But every listing of it frames it as "blockchain anomaly detection for EVE Frontier." A buyer looking for fintech fraud detection, supply chain integrity monitoring, or SCADA anomaly detection won't find it and wouldn't recognize it as applicable if they did.

**Frontier Watch is a single-purpose dashboard.** The pattern — real-time operational intel with anomaly overlays — is reusable for dozens of vertical dashboards. Currently it's a website about one game.

**aicards.fun is a working Sui gacha that nobody outside EVE will encounter.** It's the cleanest implementation of NFT attestation and on-chain rewards you have, and it's labeled as a card game.

### 1.3 The repositioning

The stack disassembles into three generic components with clean names:

| Current | New | Role in primitive stack |
|---------|-----|-------------------------|
| Monolith | `arete-sentinel-core` | P4 (Anomaly Detection Engine) |
| Frontier Watch | `arete-watchtower` | Reusable dashboard template |
| aicards.fun | `arete-attest` reference implementation | P3 (Attestation) |

The EVE Frontier instances stay alive. They become reference implementations showing that the generic components work on real use cases. But the components themselves leave the EVE namespace.

### 1.4 The commercial unlock

This repositioning enables a product line: **Sentinel** (anomaly detection as a service) from the pattern-reuse playbook.

Monolith as `arete-sentinel-core` is the engine. The hackathon work already proved it handles real event streams with rule + ML hybrid detection. Detaching it from blockchain assumptions opens:

- **Fintech fraud detection** — transaction streams, unusual patterns, velocity checks
- **Crypto forensics** — the current domain, now positionable as a standalone offering
- **Supply chain integrity** — logistics event streams (your Toyota domain directly)
- **Industrial SCADA** — sensor anomalies in manufacturing environments
- **Audit logs** — security event stream analysis

Same engine, five verticals. The 31 rules become templates that vertical buyers extend for their domain.

### 1.5 The hackathon's ongoing role

EVE Frontier instances continue running. They serve three purposes:

1. **Reference implementation** — "we deployed this in production, here's the live URL"
2. **Testbed** — new features get proven in EVE first before shipping to commercial customers
3. **Community** — the EVE audience is a passionate, technical early-adopter community that gives real feedback

Keep them. Maintain them. But stop letting them define the product.

---

## Part 2: Build Blueprint

### 2.1 Extraction: Monolith → arete-sentinel-core

```
arete-sentinel-core
├── core/
│   ├── engine.py              # Rule + ML evaluation loop
│   ├── events.py              # Event schema (generic, not blockchain-specific)
│   └── anomalies.py           # Anomaly output structure
├── rules/
│   ├── dsl.py                 # Rule definition language
│   ├── evaluator.py           # Rule runtime
│   └── templates/             # Domain-agnostic templates + vertical packs
│       ├── generic/
│       ├── blockchain/        # Current 31 rules live here
│       ├── fintech/
│       ├── supply_chain/
│       └── scada/
├── ml/
│   ├── models.py              # Anomaly detection models
│   ├── training.py            # Training pipeline
│   └── inference.py           # Real-time inference
├── outputs/
│   ├── signed_alert.py        # Integration with arete-ledger (P1)
│   └── notifications.py       # Channel adapters
└── adapters/
    ├── blockchain_sui.py      # Sui-specific ingestion (current)
    ├── blockchain_eth.py      # Ethereum ingestion (future)
    ├── log_stream.py          # Generic log ingestion
    └── csv_batch.py           # Batch file ingestion
```

The engine becomes domain-agnostic. Blockchain-specific logic moves to adapters and rule packs. New verticals add new adapters and rule packs without touching the core.

### 2.2 Extraction: Frontier Watch → arete-watchtower

Frontier Watch is a Next.js dashboard. Extract the pattern:

```
arete-watchtower (template, not deployed product)
├── src/
│   ├── components/
│   │   ├── AnomalyFeed.tsx    # Real-time anomaly stream
│   │   ├── MetricCard.tsx     # KPI displays
│   │   ├── TimelineChart.tsx  # Time-series visualization
│   │   └── AlertDetail.tsx    # Drill-down view
│   ├── layouts/
│   │   └── OpsIntel.tsx       # The full dashboard layout
│   └── adapters/
│       └── sentinel.ts        # Connects to arete-sentinel-core
├── examples/
│   ├── eve_frontier/          # Current deployment
│   ├── generic_ops/           # Template for new verticals
│   └── fintech_fraud/         # Sample fintech deployment
└── README.md                  # How to adapt to a new vertical
```

The existing Frontier Watch deployment continues to run at its current URL. New deployments reuse the template.

### 2.3 Extraction: aicards.fun → arete-attest reference

aicards.fun is a working Sui gacha. It's also the cleanest P3 (Attestation) implementation you have. The attestation primitive extracts the core pattern:

```
arete-attest (P3)
├── sui/
│   ├── contracts/             # Move contracts for attestation
│   ├── issuer.ts              # Issue attestation flow
│   └── verifier.ts            # Verification flow
├── sdk/
│   ├── typescript/            # TS SDK for consumers
│   └── python/                # Python SDK for issuers
├── examples/
│   ├── aicards_fun/           # Current deployment
│   ├── credential_issuance/   # Credentia (B) use case
│   └── skill_attestation/     # AISkill Arena use case
└── spec/
    └── attestation_format.md  # The format spec (aligns with arete-context)
```

aicards.fun continues to operate as a game. The underlying contracts and flow become the reference for any attestation use case.

### 2.4 Migration order

**Weeks 1-2: Monolith extraction**
- Separate blockchain-specific code from core engine
- Move the 31 rules into rules/templates/blockchain/
- Generic event schema definition
- New README positioning as general-purpose anomaly detection

**Weeks 3-4: Sentinel product surface**
- Landing page for Sentinel (product line D)
- Documentation for new verticals
- First non-blockchain adapter (fintech fraud seems highest-value given market)
- Two new rule packs for a non-blockchain vertical

**Weeks 5-6: Frontier Watch template extraction**
- Generic dashboard template repo
- Documentation for adapting to a new vertical
- Sample deployment for a non-EVE vertical

**Weeks 7-8: aicards contracts generalized**
- Abstract the attestation contracts
- SDKs in TS and Python
- Aligned with arete-context attestation format

**Ongoing: Hackathon deployments maintained**
- EVE Frontier instances continue running
- New features proven on EVE before commercial deployment
- Community feedback loop preserved

### 2.5 What to kill explicitly

- **The "Aegis Stack" brand** in public materials. It stays as an internal reference to the hackathon submission but commercial materials use the component names.
- **Monolith as a name** in commercial contexts. Use `arete-sentinel-core` or Sentinel in pitch materials.
- **EVE-specific language** in component documentation that isn't in the EVE adapters.
- **Hackathon framing as the lead** on resume/portfolio. The hackathon is a supporting credential, not the headline. The headline is "built a generalized anomaly detection engine."

### 2.6 What to add

- **Sentinel landing page** at a clean URL, clearly positioned for multiple verticals
- **First commercial vertical target documentation** (recommend fintech fraud as the wedge given market size and your existing expertise)
- **Case study doc** on the EVE Frontier deployment, repositioned as "real-world production deployment with X million events processed"
- **Rule-writing guide** so customers can extend the engine without requiring your involvement
- **Attestation format alignment with arete-context** so bundles and attestations interoperate

### 2.7 Success criteria

The Aegis Stack rework succeeds if:

1. Monolith is running under a new package name (`arete-sentinel-core`) within four weeks
2. At least one non-blockchain adapter is implemented by week eight
3. Sentinel has a public landing page positioning it for at least three verticals by end of Q3
4. At least one real commercial conversation about Sentinel happens by end of Q3
5. The hackathon deployments continue running with no degradation during the migration

### 2.8 Integration with primitive stack

The Aegis Stack extraction produces three primitives and one template:

- **`arete-sentinel-core` = P4 (Anomaly Detection Engine)**
- **`arete-attest` = P3 (Attestation)**
- **`arete-watchtower` = reusable dashboard template**
- **`arete-ledger` signed alert outputs = P1 consumer**

Products that consume these:

- **Sentinel (product line D)** — direct productization of P4
- **Credentia (product line B)** — uses P3 for attestation
- **Ledger (product line A)** — uses P4 for AI decision anomaly detection and P3 for attestation
- **Gemba (product line E)** — industrial deployments use P4 for process monitoring

### 2.9 The fintech wedge (specific recommendation)

If Sentinel is going to be a product, it needs a wedge vertical. Recommendation: **fintech fraud detection**.

Reasoning:

- Large, mature market with established willingness to pay
- Your blockchain experience is adjacent and credible (crypto is fintech-adjacent)
- Your Toyota operations background gives you TPS/standard-work credibility for talking to risk teams
- Regulatory tailwinds (bank AI governance pressure) create urgency
- Lower enterprise sales complexity than SCADA or supply chain (fintech buys faster)

Alternative wedges:

- Crypto forensics as standalone (narrower market but you're already expert)
- Supply chain integrity (larger market but longer sales cycles)
- SCADA/industrial (your domain but requires deep industrial sales motion)

Fintech is the recommendation because it's the shortest path from "I have an engine" to "I have a customer."

---

## Part 3: What to do this week

1. **Rename Monolith to `arete-sentinel-core` in your own planning** — internal commitment to the repositioning before any code moves.
2. **Audit the existing Monolith codebase** and identify which files are domain-agnostic vs. blockchain-specific. This audit drives the extraction plan.
3. **Draft the generic event schema.** This is the first architectural decision that gates everything else. Get it on paper.
4. **Pick the fintech wedge or push back** with a specific alternative. Writing the decision down commits you.
5. **Write one-paragraph repositioning statements** for each of the three components. These become the new READMEs and the start of commercial copy.
