"""LLM narrator — generates plain English descriptions of anomalies.

Uses Anthropic API (claude-sonnet-4-5). Only called AFTER detection, never during.
Caches results per anomaly_id — never re-calls for same anomaly.
Falls back to template text if API unavailable.
"""

import json
import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You write terse anomaly briefs for EVE Frontier chain engineers.

Rules:
- 2-3 sentences MAX. Never exceed 50 words.
- Lead with WHAT happened, then WHY it matters.
- No preamble, no hedging, no filler.
- Use exact object IDs and values from the evidence.
- State facts. Do not speculate."""

# Template fallbacks when LLM is unavailable
TEMPLATES: dict[str, str] = {
    "ORPHAN_OBJECT": (
        "A chain event was recorded for an object that has no creation record in the "
        "monitoring system. This may indicate the object was created before monitoring "
        "started, or that a creation event was missed by the indexer."
    ),
    "RESURRECTION": (
        "An object that was previously marked as destroyed showed new activity on chain. "
        "This is a critical data integrity issue — destroyed objects should not produce "
        "new events. Either the destruction was incorrectly recorded, or the object's "
        "state was reset without proper chain events."
    ),
    "STATE_GAP": (
        "An object transitioned between states without going through the expected "
        "intermediate states. The state machine should enforce valid transitions, "
        "so this may indicate a contract bug or a missed intermediate event."
    ),
    "STUCK_OBJECT": (
        "An assembly has been in a transitional state longer than expected with no "
        "new chain activity. This may indicate a stuck transaction or a failed "
        "state change that left the object in limbo."
    ),
    "SUPPLY_DISCREPANCY": (
        "Fuel or item quantities changed between snapshots without corresponding "
        "chain events. Either events were missed by the indexer, or the contract "
        "modified state without emitting the expected events."
    ),
    "UNEXPLAINED_DESTRUCTION": (
        "An object disappeared from the API between polling cycles with no "
        "destruction or unanchor event on chain. The object may have been removed "
        "through a code path that doesn't emit events."
    ),
    "DUPLICATE_MINT": (
        "Multiple events with identical characteristics were found for the same "
        "transaction. This could indicate double-processing in the event pipeline "
        "or a genuine duplicate event emission from the contract."
    ),
    "NEGATIVE_BALANCE": (
        "A fuel or resource balance was found to be negative, which should be "
        "mathematically impossible. This indicates an arithmetic error in the "
        "contract or an accounting inconsistency in the state."
    ),
    "CONTRACT_STATE_MISMATCH": (
        "The state recorded by the last transition event does not match the current "
        "API-reported state. Either an intermediate state change was not recorded, "
        "or the API and chain have diverged."
    ),
    "PHANTOM_ITEM_CHANGE": (
        "Object properties changed between consecutive snapshots with no chain events "
        "in the observation window. Either the indexer missed events, or the state "
        "was modified through a code path that doesn't emit on-chain records."
    ),
    "UNEXPLAINED_OWNERSHIP_CHANGE": (
        "Object ownership changed between snapshots without a transfer event on chain. "
        "This is a critical issue — ownership changes must always have an on-chain record "
        "for security and auditability."
    ),
    "FREE_GATE_JUMP": (
        "A gate jump was executed without a corresponding fuel consumption event in the "
        "same transaction. Gates should consume fuel on each use. This may indicate a "
        "contract bug allowing free travel, or a missing FuelEvent emission."
    ),
    "FAILED_GATE_TRANSPORT": (
        "Fuel was consumed on a gate but no jump event was recorded in the same "
        "transaction. The player paid fuel but was not transported. This could indicate "
        "a failed transaction that didn't properly refund, or a gate link issue."
    ),
    "DUPLICATE_TRANSACTION": (
        "A transaction emitted an unusually high number of events. While complex "
        "transactions can produce many events, the count exceeds normal patterns "
        "and may indicate processing issues."
    ),
    "BLOCK_PROCESSING_GAP": (
        "A large gap was detected in the sequence of processed blocks. Events in the "
        "missing blocks may have been skipped. This likely indicates an RPC or indexer "
        "availability issue rather than a chain problem."
    ),
    "OWNERCAP_TRANSFER": (
        "An OwnerCap object was transferred to a new address. This indicates "
        "ownership delegation — the original SSU owner retains inventory access "
        "but another entity now holds the capability object."
    ),
    "OWNERCAP_DELEGATION": (
        "Object ownership changed between snapshots with a corresponding transfer "
        "event on chain. This is a deliberate delegation, not an unexplained change."
    ),
    "DUPLICATE_KILLMAIL": (
        "The same victim was killed multiple times within a short window. "
        "This may indicate a duplicate event emission or a genuine double-kill."
    ),
    "THIRD_PARTY_KILL_REPORT": (
        "A kill was reported to chain by someone other than the killer. "
        "While valid, third-party reporting is unusual and worth tracking."
    ),
}


async def narrate_anomaly(
    anomaly_type: str,
    evidence: dict,
    rule_id: str,
    severity: str,
    api_key: str = "",
    model: str = "claude-sonnet-4-5-20250514",
) -> str:
    """Generate a plain English description of an anomaly.

    Uses Anthropic API if api_key is provided, otherwise falls back to templates.
    """
    if not api_key:
        return _template_narration(anomaly_type, evidence)

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key)

        user_message = json.dumps(
            {
                "anomaly_type": anomaly_type,
                "severity": severity,
                "rule_id": rule_id,
                "evidence": evidence,
            },
            indent=2,
        )

        response = await client.messages.create(
            model=model,
            max_tokens=100,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        narration = response.content[0].text.strip()
        logger.info("LLM narration generated for %s (%d chars)", anomaly_type, len(narration))
        return narration

    except Exception as e:
        logger.warning("LLM narration failed, using template: %s", e)
        return _template_narration(anomaly_type, evidence)


def _template_narration(anomaly_type: str, evidence: dict) -> str:
    """Generate narration from templates when LLM is unavailable."""
    base = TEMPLATES.get(anomaly_type, f"Anomaly of type {anomaly_type} was detected.")

    # Append key evidence details
    description = evidence.get("description", "")
    if description and description != base:
        return f"{base}\n\nSpecifics: {description}"

    return base
