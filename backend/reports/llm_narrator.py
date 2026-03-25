"""LLM narrator — generates plain English descriptions of anomalies.

Uses Anthropic API (claude-sonnet-4-5). Only called AFTER detection, never during.
Caches results per anomaly_id — never re-calls for same anomaly.
Falls back to template text if API unavailable.
"""

import json
import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a frontier intelligence analyst writing field dispatches "
    "for chain operatives.\n\n"
    "Voice: Terse. Grim. Like a telegraph from a deep-space outpost "
    "that's seen too much.\n"
    "Think: military intel briefing meets frontier marshal's incident log.\n\n"
    "Rules:\n"
    "- 2-3 sentences MAX. Never exceed 50 words.\n"
    "- Lead with WHAT happened, then WHY it matters to anyone alive out here.\n"
    "- Reference object IDs and values from the evidence — be precise.\n"
    "- No preamble, no hedging, no corporate language.\n"
    "- State facts like you're filing them before the next blackout.\n"
    '- Use frontier language: "wreckage", "dark", "adrift", "burned", '
    '"seized", not "inconsistency" or "discrepancy".'
)

# Template fallbacks when LLM is unavailable
TEMPLATES: dict[str, str] = {
    "ORPHAN_OBJECT": (
        "Ghost signal — moderate concern. Chain event references an object with no "
        "birth record in our ledgers. May indicate an indexer gap or pre-deployment "
        "artifact. Review the event source and check for backfill gaps."
    ),
    "RESURRECTION": (
        "Critical alert — wreckage is transmitting. An asset confirmed destroyed just "
        "resumed chain activity. This is an immediate, severe integrity violation. "
        "Investigate all post-destruction transactions and escalate to verify chain state."
    ),
    "STATE_GAP": (
        "High priority — missing trajectory. Object jumped between states with no "
        "valid intermediate waypoints on record. This is a notable concern that "
        "requires attention. Examine the chain between snapshot timestamps and verify "
        "the transition map."
    ),
    "STUCK_OBJECT": (
        "Moderate concern — assembly adrift. Caught in a transitional state with no "
        "new signals. May indicate a stuck transaction or abandoned state change. "
        "Monitor for activity and check if the wallet has gas."
    ),
    "SUPPLY_DISCREPANCY": (
        "High priority — phantom ledger. Fuel or cargo quantities shifted between "
        "sweeps with no chain events to explain the change. This is a concerning "
        "discrepancy. Investigate the chain for missing deposit or withdrawal events "
        "and verify fuel burn rates."
    ),
    "UNEXPLAINED_DESTRUCTION": (
        "High priority — asset vanished between polling sweeps. No destruction event, "
        "no unanchor, no wreckage. This is a suspicious disappearance that requires "
        "attention. Check the next API poll for reappearance and examine the chain "
        "for removal events."
    ),
    "DUPLICATE_MINT": (
        "High priority — double stamp. Same asset minted twice in one transaction. "
        "This is a notable concern for data integrity. Review both event receipts "
        "and verify the deduplication layer."
    ),
    "NEGATIVE_BALANCE": (
        "Critical alert — impossible arithmetic. A fuel or resource balance dropped "
        "below zero. This is an immediate, severe violation of conservation laws. "
        "Investigate the contract math and escalate — trace historical fuel events "
        "to find the source."
    ),
    "CONTRACT_STATE_MISMATCH": (
        "High priority — forked reality. Chain and world API report different states. "
        "This is a concerning divergence that requires attention. Verify by querying "
        "chain state directly and check for API cache lag."
    ),
    "PHANTOM_ITEM_CHANGE": (
        "High priority — shadow inventory. Cargo manifest changed between snapshots "
        "with no chain events in the window. This is a suspicious, notable change. "
        "Investigate all events touching this object and check for cursor gaps in "
        "event ingestion."
    ),
    "UNEXPLAINED_OWNERSHIP_CHANGE": (
        "Critical alert — silent seizure. Ownership changed hands with no transfer "
        "event on chain. This is an immediate, severe threat — every legitimate "
        "handoff gets recorded. Investigate immediately and verify no admin bypass "
        "occurred."
    ),
    "FREE_GATE_JUMP": (
        "High priority — toll runner. Gate jump executed but fuel meter didn't move. "
        "This is a concerning anomaly that requires attention. Examine the transaction "
        "for fuel consumption events and verify gate configuration."
    ),
    "FAILED_GATE_TRANSPORT": (
        "High priority — gate tax lost. Fuel was burned but no jump completed. "
        "This is a notable concern for player assets. Review the transaction logs "
        "and check gate link status at time of transit."
    ),
    "DUPLICATE_TRANSACTION": (
        "Moderate concern — event storm. A single transaction fired an abnormal "
        "number of events. Monitor for recurrence and review whether this is a "
        "legitimate complex operation or an ingestion issue."
    ),
    "BLOCK_PROCESSING_GAP": (
        "High priority — blind spot. Large gap in processed block sequence. "
        "This is a concerning surveillance blackout. Investigate the RPC node "
        "availability and examine the missing block range for contract events."
    ),
    "OWNERCAP_TRANSFER": (
        "Notable concern — title deed transfer. An OwnerCap object changed hands. "
        "Review the transfer context and monitor who is accumulating capability "
        "objects in this region."
    ),
    "OWNERCAP_DELEGATION": (
        "Low priority — routine delegation confirmed on chain. Transfer event "
        "matches the snapshot change. Informational only, but consider tracking "
        "accumulation patterns."
    ),
    "DUPLICATE_KILLMAIL": (
        "Moderate concern — double tap. Same target registered as killed twice. "
        "Verify the receipts and check for chain event deduplication issues."
    ),
    "THIRD_PARTY_KILL_REPORT": (
        "Low priority — witness report. Kill logged by a third party, which is "
        "routine but unusual. Review who filed the report and flag if the pattern "
        "recurs."
    ),
}


async def narrate_anomaly(
    anomaly_type: str,
    evidence: dict,
    rule_id: str,
    severity: str,
    api_key: str = "",
    model: str = "claude-sonnet-4-5-20250514",
) -> dict:
    """Generate a plain English description of an anomaly.

    Uses Anthropic API if api_key is provided, otherwise falls back to templates.

    Returns a dict with keys:
        - narration: str  (the plain English text)
        - input_tokens: int | None
        - output_tokens: int | None
    """
    if not api_key:
        return {
            "narration": _template_narration(anomaly_type, evidence),
            "input_tokens": None,
            "output_tokens": None,
        }

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
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        logger.info(
            "LLM narration generated for %s (%d chars, %d/%d tokens)",
            anomaly_type,
            len(narration),
            input_tokens,
            output_tokens,
        )
        return {
            "narration": narration,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    except Exception as e:
        logger.warning("LLM narration failed, using template: %s", e)
        return {
            "narration": _template_narration(anomaly_type, evidence),
            "input_tokens": None,
            "output_tokens": None,
        }


def _template_narration(anomaly_type: str, evidence: dict) -> str:
    """Generate narration from templates when LLM is unavailable."""
    base = TEMPLATES.get(anomaly_type, f"Anomaly of type {anomaly_type} was detected.")

    # Append key evidence details
    description = evidence.get("description", "")
    if description and description != base:
        return f"{base}\n\nSpecifics: {description}"

    return base
