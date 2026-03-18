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
        "Ghost signal. Chain event references an object with no birth record in our "
        "ledgers. Either it predates our watch, or something slipped past the indexer "
        "in the dark."
    ),
    "RESURRECTION": (
        "Wreckage is transmitting. An asset confirmed destroyed just resumed chain "
        "activity. Destroyed objects don't come back — not without someone rewriting "
        "history. Treat as hostile until proven otherwise."
    ),
    "STATE_GAP": (
        "Missing trajectory. Object jumped between states with no flight path on "
        "record. The state machine should enforce every waypoint. Something punched "
        "through the gate without stopping."
    ),
    "STUCK_OBJECT": (
        "Assembly adrift. Caught in a transitional state with no new signals. "
        "Could be a stuck transaction or a state change that died mid-flight, "
        "leaving the hull in limbo."
    ),
    "SUPPLY_DISCREPANCY": (
        "Phantom ledger. Fuel or cargo quantities shifted between sweeps with no "
        "chain events to explain it. Resources don't move themselves out here. "
        "Either the indexer blinked, or someone found a back door."
    ),
    "UNEXPLAINED_DESTRUCTION": (
        "Asset vanished between polling sweeps. No destruction event, no unanchor, "
        "no wreckage. Gone like it was never here. Whatever removed it didn't "
        "leave a trace on chain."
    ),
    "DUPLICATE_MINT": (
        "Double stamp. Same asset minted twice in one transaction. Could be a "
        "pipeline echo, could be the contract stuttering. Either way, there's "
        "one too many of something that should be unique."
    ),
    "NEGATIVE_BALANCE": (
        "Impossible arithmetic. A fuel or resource balance dropped below zero. "
        "Conservation laws don't bend out here — this points to a contract math "
        "error or corrupted state. Red alert."
    ),
    "CONTRACT_STATE_MISMATCH": (
        "Forked reality. The last transition event tells one story, the API tells "
        "another. Chain and world have diverged. Someone's lying, or something "
        "changed in the dark between reads."
    ),
    "PHANTOM_ITEM_CHANGE": (
        "Shadow inventory. Cargo manifest changed between snapshots with no chain "
        "events in the window. Items don't rearrange themselves. Something touched "
        "this inventory off the books."
    ),
    "UNEXPLAINED_OWNERSHIP_CHANGE": (
        "Silent seizure. Ownership of this asset changed hands with no transfer "
        "event on chain. Out here, every handoff gets recorded — or it's a theft. "
        "Investigate immediately."
    ),
    "FREE_GATE_JUMP": (
        "Toll runner. Gate jump executed, fuel meter didn't move. Gates burn fuel — "
        "that's the law. Someone found a way through without paying, or the "
        "FuelEvent never fired. Either way, the gate's integrity is compromised."
    ),
    "FAILED_GATE_TRANSPORT": (
        "Gate tax lost. Fuel was burned at the gate but no jump completed. The "
        "traveler paid the toll and never arrived. Failed transaction without "
        "refund, or a broken gate link. Someone's out fuel and still stranded."
    ),
    "DUPLICATE_TRANSACTION": (
        "Event storm. A single transaction fired an abnormal number of events. "
        "Complex operations can be noisy, but this exceeds normal patterns. "
        "Could be processing issues or something deliberately flooding the pipe."
    ),
    "BLOCK_PROCESSING_GAP": (
        "Blind spot. Large gap in processed block sequence — our surveillance "
        "went dark during this window. Any events in those missing blocks are "
        "unaccounted for. Likely an RPC dropout, but what happened while we "
        "weren't watching?"
    ),
    "OWNERCAP_TRANSFER": (
        "Title deed transfer. An OwnerCap object changed hands. The original "
        "owner keeps inventory access, but someone else now holds the keys. "
        "Could be legitimate delegation — or the first move in a hostile takeover."
    ),
    "OWNERCAP_DELEGATION": (
        "Ownership delegation confirmed on chain. Transfer event matches the "
        "snapshot change — this one's deliberate, not a ghost. Still worth "
        "tracking who's accumulating capability objects."
    ),
    "DUPLICATE_KILLMAIL": (
        "Double tap. Same target registered as killed twice in rapid succession. "
        "Either the chain stuttered and echoed the event, or someone genuinely "
        "killed the same mark twice. Verify the receipts."
    ),
    "THIRD_PARTY_KILL_REPORT": (
        "Witness report. This kill was logged to chain by someone other than "
        "the shooter. Third-party reporting isn't forbidden, but it's unusual "
        "enough to warrant a closer look at who's watching and why."
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
