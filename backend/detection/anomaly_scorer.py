"""Anomaly scorer — assigns severity and category to detected anomalies."""

SEVERITY_WEIGHTS: dict[str, int] = {
    "CRITICAL": 100,
    "HIGH": 60,
    "MEDIUM": 30,
    "LOW": 10,
}

# Frontier display names: rule_id → (display_name, tagline)
RULE_DISPLAY: dict[str, tuple[str, str]] = {
    # Continuity
    "C1": ("Ghost Signal", "Unregistered object broadcasting on chain"),
    "C2": ("Lazarus Event", "Destroyed asset resumed transmission"),
    "C3": ("Missing Trajectory", "Object jumped states — no flight path recorded"),
    "C4": ("Dead Drift", "Assembly adrift in transitional state — no signs of life"),
    # Economic
    "E1": ("Phantom Ledger", "Resources shifted without a paper trail"),
    "E2": ("Vanishing Act", "Asset erased between sweeps — no wreckage, no record"),
    "E3": ("Double Stamp", "Duplicate mint detected — same asset, same transaction"),
    "E4": ("Negative Mass", "Balance went sub-zero — impossible arithmetic"),
    # Assembly
    "A1": ("Forked State", "Chain says one thing, API says another"),
    "A2": ("Toll Runner", "Gate jump executed without paying fuel"),
    "A3": ("Gate Tax Lost", "Fuel burned at gate — traveler never arrived"),
    "A4": ("Shadow Inventory", "Cargo shifted without manifest update"),
    "A5": ("Silent Seizure", "Ownership changed with no transfer on record"),
    # Sequence
    "S1": ("Broken Ledger", "Event sequence integrity compromised"),
    "S2": ("Event Storm", "Transaction emitted suspiciously high event count"),
    "S3": ("Sequence Drift", "Events arrived out of expected order"),
    "S4": ("Blind Spot", "Block processing gap — surveillance dark during window"),
    # POD
    "P1": ("Chain Divergence", "Local state diverged from on-chain truth"),
    # Killmail
    "K1": ("Double Tap", "Same target killed twice in rapid succession"),
    "K2": ("Witness Report", "Kill logged by a third party, not the shooter"),
    # Coordinated buying
    "CB1": ("Convoy Forming", "Multiple wallets transacting in same region — coordinated movement"),
    "CB2": ("Fleet Mobilization", "Large-scale coordinated acquisition — fleet action likely"),
    # Object version
    "OV1": ("State Rollback", "Object version decreased — history was rewritten"),
    "OV2": ("Unauthorized Mod", "State modified without proper version increment"),
    # Wallet concentration
    "WC1": ("Resource Baron", "Single wallet hoarding disproportionate system resources"),
    # Config change
    "CC1": ("Contract Tamper", "World contract configuration altered"),
    # Inventory audit
    "IA1": ("Matter Violation", "Items created or destroyed outside conservation laws"),
    # Bot pattern
    "BP1": ("Drone Signature", "Automated transaction pattern detected"),
    # Tribe hopping
    "TH1": ("Drifter", "Rapid tribe changes — loyalty to no flag"),
    # Engagement session
    "ES1": ("Orphaned Kill", "Killmail with no preceding combat events"),
    "ES2": ("Phantom Kill", "Victim had zero chain history — materialized to die"),
    # Dead assembly
    "DA1": ("Derelict", "Assembly dark for 30+ days — presumed abandoned"),
    # Velocity
    "EV1": ("Gold Rush", "Economic activity spiking — something's happening here"),
    "EV2": ("Market Silence", "Trade volume collapsed — region going cold"),
    # Ownership
    "OC1": ("Title Deed Transfer", "OwnerCap handed to a new address"),
}

ANOMALY_CATEGORIES: dict[str, str] = {
    "EXPLOIT_VECTOR": "CRITICAL",
    "DATA_INTEGRITY": "CRITICAL",
    "PLAYER_LOSS": "HIGH",
    "STATE_INCONSISTENCY": "HIGH",
    "BEHAVIORAL": "MEDIUM",
    "PERFORMANCE": "LOW",
}

# Maps rule_id → (severity, category)
RULE_CLASSIFICATION: dict[str, tuple[str, str]] = {
    # Continuity checker
    "C1": ("MEDIUM", "STATE_INCONSISTENCY"),
    "C2": ("CRITICAL", "DATA_INTEGRITY"),
    "C3": ("HIGH", "STATE_INCONSISTENCY"),
    "C4": ("MEDIUM", "PERFORMANCE"),
    # Economic checker
    "E1": ("HIGH", "DATA_INTEGRITY"),
    "E2": ("HIGH", "STATE_INCONSISTENCY"),
    "E3": ("CRITICAL", "EXPLOIT_VECTOR"),
    "E4": ("CRITICAL", "DATA_INTEGRITY"),
    # Assembly checker
    "A1": ("HIGH", "STATE_INCONSISTENCY"),
    "A2": ("HIGH", "EXPLOIT_VECTOR"),
    "A3": ("MEDIUM", "PLAYER_LOSS"),
    "A4": ("HIGH", "STATE_INCONSISTENCY"),
    "A5": ("CRITICAL", "DATA_INTEGRITY"),
    # Sequence checker
    "S1": ("CRITICAL", "DATA_INTEGRITY"),
    "S2": ("MEDIUM", "DATA_INTEGRITY"),
    "S3": ("HIGH", "STATE_INCONSISTENCY"),
    "S4": ("MEDIUM", "PERFORMANCE"),
    # POD checker
    "P1": ("CRITICAL", "EXPLOIT_VECTOR"),
    # Killmail checker
    "K1": ("HIGH", "DATA_INTEGRITY"),
    "K2": ("MEDIUM", "DATA_INTEGRITY"),
    # Coordinated buying checker
    "CB1": ("MEDIUM", "BEHAVIORAL"),
    "CB2": ("CRITICAL", "BEHAVIORAL"),
    # Object version checker
    "OV1": ("CRITICAL", "DATA_INTEGRITY"),
    "OV2": ("HIGH", "DATA_INTEGRITY"),
    # Wallet concentration checker
    "WC1": ("HIGH", "BEHAVIORAL"),
    # Config change checker
    "CC1": ("CRITICAL", "DATA_INTEGRITY"),
    # Inventory audit checker
    "IA1": ("CRITICAL", "EXPLOIT_VECTOR"),
    # Bot pattern checker
    "BP1": ("MEDIUM", "BEHAVIORAL"),
    # Tribe hopping checker
    "TH1": ("MEDIUM", "BEHAVIORAL"),
    # Engagement session checker
    "ES1": ("HIGH", "DATA_INTEGRITY"),
    "ES2": ("CRITICAL", "DATA_INTEGRITY"),
    # Dead assembly checker
    "DA1": ("LOW", "PERFORMANCE"),
    # Velocity checker
    "EV1": ("HIGH", "BEHAVIORAL"),
    "EV2": ("MEDIUM", "PERFORMANCE"),
    # Ownership checker
    "OC1": ("MEDIUM", "BEHAVIORAL"),
}


def classify_anomaly(rule_id: str) -> tuple[str, str]:
    """Return (severity, category) for a given rule ID."""
    return RULE_CLASSIFICATION.get(rule_id, ("LOW", "BEHAVIORAL"))


def display_name(rule_id: str) -> str:
    """Return the frontier display name for a rule ID."""
    entry = RULE_DISPLAY.get(rule_id)
    return entry[0] if entry else rule_id


def display_tagline(rule_id: str) -> str:
    """Return the frontier tagline for a rule ID."""
    entry = RULE_DISPLAY.get(rule_id)
    return entry[1] if entry else ""


def severity_weight(severity: str) -> int:
    """Return numeric weight for a severity level."""
    return SEVERITY_WEIGHTS.get(severity, 0)
