# MONOLITH — Competitive Positioning & Feature Completion
## CLAUDE.md Handoff for Claude Code

**Repo:** AreteDriver/monolith  
**Deadline:** March 31, 2026  
**Status:** Map, anomaly feed, and heatmap are live. Adding coordinated buying signal layer.

---

## Strategic Context

A competitor project (The Rift Broker) is building a cryptographic intel marketplace for EVE Frontier. Their stated endgame is a "live intelligence heat-map of the whole Eve Frontier universe."

**Monolith already has that heatmap. And more.**

| Feature | Rift Broker | Monolith |
|---|---|---|
| Intel marketplace | ✅ Their core | ❌ Not our game |
| ZK proof verification | ✅ Their moat | ❌ Not needed |
| Intel heatmap | 🔜 Their endgame | ✅ Already live |
| Anomaly detection | ❌ Conflict of interest | ✅ Already live |
| Coordinated buying signal | ❌ | 🔜 Add this |

**The positioning:** Rift Broker sells intel. Monolith watches the sellers. They cannot build anomaly detection against their own marketplace without conflict of interest. That's our moat.

---

## What Monolith Currently Has

- ✅ Map layer (live)
- ✅ Anomaly feed (live)
- ✅ Intel heatmap (live)
- ✅ Bug reporting (live)
- ✅ Sui GraphQL data pipeline (live)

---

## What to Add

### CoordinatedBuyingDetector

Plugs into the existing anomaly feed. No new infrastructure.

**What it detects:** Multiple wallets purchasing intel for the same region within a 10-minute window — leading indicator of an imminent fleet action.

**Thresholds:**
- 3+ unique buyers, same region, 10 min → `medium` — "Coordinated intel acquisition detected"
- 5+ unique buyers OR 3+ buyers all buying `fleet` type intel → `critical` — "FLEET ACTION LIKELY"

**Data model:**
```python
@dataclass
class IntelPurchaseEvent:
    event_id: str
    timestamp: datetime
    buyer_address: str       # Sui wallet
    scout_address: str       # who listed the intel
    region: str
    intel_type: str          # "fleet" | "resource" | "base" | "unknown"
    price_sui: float
    listing_hash: str

@dataclass
class AnomalySignal:
    signal_id: str
    signal_type: str         # "coordinated_buying"
    severity: str            # "medium" | "critical"
    confidence: float
    region: str
    description: str
    buyer_count: int
    fleet_intel_count: int
    detected_at: datetime
    raw_buyers: list[str]
```

**Core logic:**
```python
class CoordinatedBuyingDetector:
    def __init__(self, window_minutes=10):
        self.window_minutes = window_minutes
        self._purchase_log = defaultdict(list)  # region -> [events]

    def ingest(self, event: IntelPurchaseEvent) -> None:
        self._purchase_log[event.region].append(event)
        self._prune(event.region)

    def _prune(self, region: str) -> None:
        cutoff = datetime.utcnow() - timedelta(minutes=self.window_minutes)
        self._purchase_log[region] = [
            e for e in self._purchase_log[region] if e.timestamp >= cutoff
        ]

    def detect(self, region: str) -> AnomalySignal | None:
        events = self._purchase_log.get(region, [])
        unique_buyers = set(e.buyer_address for e in events)
        fleet_intel_count = sum(1 for e in events if e.intel_type == "fleet")
        buyer_count = len(unique_buyers)

        if buyer_count >= 5 or (buyer_count >= 3 and fleet_intel_count >= 3):
            severity = "critical"
            confidence = 0.92
            description = f"FLEET ACTION LIKELY — {buyer_count} buyers acquiring intel on {region}"
        elif buyer_count >= 3:
            severity = "medium"
            confidence = 0.65
            description = f"Coordinated intel acquisition detected in {region}"
        else:
            return None
        # build and return AnomalySignal
```

**Wire into existing Sui GraphQL polling loop** — call `ingest()` on each purchase event, call `detect()` after each ingest, push result to existing anomaly feed if not None.

**Add one endpoint:**
```
GET /anomaly/coordinated-buying?region=X&severity=Y
```

---

### Heatmap Reframe (Zero Code)

The existing heatmap shows intel activity. When CoordinatedBuyingDetector signals overlay on it, it becomes a **threat heatmap** — showing not just where intel exists but where fleets are staging.

**In the demo video and submission, call it a "threat heatmap" explicitly.** This is a direct counter to Rift Broker's stated endgame and requires no additional code.

---

## Fallback If Rift Broker Data Isn't On-Chain

Their marketplace may not be live during the hackathon window. If purchase events aren't available:

- Use any cluster of Sui wallet transactions targeting the same region within 10 minutes as a proxy
- Detector logic is identical, only the event type filter changes
- Demo narration: *"When intel purchases cluster on a region, Monolith flags it as a potential fleet staging signal"*

---

## Build Order

1. Add `IntelPurchaseEvent` to existing event models
2. Implement `CoordinatedBuyingDetector` as standalone module
3. Write 4 unit tests (below threshold, medium, critical, pruning)
4. Wire into existing Sui GraphQL polling loop
5. Add `/anomaly/coordinated-buying` endpoint
6. Confirm signal appears in existing anomaly feed
7. Confirm heatmap reflects signal intensity
8. Record demo video

---

## Demo Video Narrative

*"While The Rift Broker sells intel, Monolith watches the market itself — and tells you when a fleet is about to move."*

Show the coordinated buying signal firing on the threat heatmap. That's the submission's competitive stake in the ground.

---

*Aegis Stack — Monolith*  
*Hackathon deadline: March 31, 2026*
