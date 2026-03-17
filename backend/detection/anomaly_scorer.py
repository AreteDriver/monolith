"""Anomaly scorer — assigns severity and category to detected anomalies."""

SEVERITY_WEIGHTS: dict[str, int] = {
    "CRITICAL": 100,
    "HIGH": 60,
    "MEDIUM": 30,
    "LOW": 10,
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
    "S2": ("CRITICAL", "DATA_INTEGRITY"),
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
}


def classify_anomaly(rule_id: str) -> tuple[str, str]:
    """Return (severity, category) for a given rule ID."""
    return RULE_CLASSIFICATION.get(rule_id, ("LOW", "BEHAVIORAL"))


def severity_weight(severity: str) -> int:
    """Return numeric weight for a severity level."""
    return SEVERITY_WEIGHTS.get(severity, 0)
