/**
 * Frontier display names for anomaly rule IDs.
 * Mirrors backend RULE_DISPLAY in anomaly_scorer.py.
 */

const RULE_DISPLAY = {
  // Continuity
  C1: ['Ghost Signal', 'Unregistered object broadcasting on chain'],
  C2: ['Lazarus Event', 'Destroyed asset resumed transmission'],
  C3: ['Missing Trajectory', 'Object jumped states — no flight path recorded'],
  C4: ['Dead Drift', 'Assembly adrift in transitional state — no signs of life'],
  // Economic
  E1: ['Phantom Ledger', 'Resources shifted without a paper trail'],
  E2: ['Vanishing Act', 'Asset erased between sweeps — no wreckage, no record'],
  E3: ['Double Stamp', 'Duplicate mint detected — same asset, same transaction'],
  E4: ['Negative Mass', 'Balance went sub-zero — impossible arithmetic'],
  // Assembly
  A1: ['Forked State', 'Chain says one thing, API says another'],
  A2: ['Toll Runner', 'Gate jump executed without paying fuel'],
  A3: ['Gate Tax Lost', 'Fuel burned at gate — traveler never arrived'],
  A4: ['Shadow Inventory', 'Cargo shifted without manifest update'],
  A5: ['Silent Seizure', 'Ownership changed with no transfer on record'],
  // Sequence
  S1: ['Broken Ledger', 'Event sequence integrity compromised'],
  S2: ['Event Storm', 'Transaction emitted suspiciously high event count'],
  S3: ['Sequence Drift', 'Events arrived out of expected order'],
  S4: ['Blind Spot', 'Block processing gap — surveillance dark during window'],
  // POD
  P1: ['Chain Divergence', 'Local state diverged from on-chain truth'],
  // Killmail
  K1: ['Double Tap', 'Same target killed twice in rapid succession'],
  K2: ['Witness Report', 'Kill logged by a third party, not the shooter'],
  // Coordinated buying
  CB1: ['Convoy Forming', 'Multiple wallets transacting in same region — coordinated movement'],
  CB2: ['Fleet Mobilization', 'Large-scale coordinated acquisition — fleet action likely'],
  // Object version
  OV1: ['State Rollback', 'Object version decreased — history was rewritten'],
  OV2: ['Unauthorized Mod', 'State modified without proper version increment'],
  // Wallet concentration
  WC1: ['Resource Baron', 'Single wallet hoarding disproportionate system resources'],
  // Config change
  CC1: ['Contract Tamper', 'World contract configuration altered'],
  // Inventory audit
  IA1: ['Matter Violation', 'Items created or destroyed outside conservation laws'],
  // Bot pattern
  BP1: ['Drone Signature', 'Automated transaction pattern detected'],
  // Tribe hopping
  TH1: ['Drifter', 'Rapid tribe changes — loyalty to no flag'],
  // Engagement session
  ES1: ['Orphaned Kill', 'Killmail with no preceding combat events'],
  ES2: ['Phantom Kill', 'Victim had zero chain history — materialized to die'],
  // Dead assembly
  DA1: ['Derelict', 'Assembly dark for 30+ days — presumed abandoned'],
  // Velocity
  EV1: ['Gold Rush', 'Economic activity spiking — something\'s happening here'],
  EV2: ['Market Silence', 'Trade volume collapsed — region going cold'],
  // Ownership
  OC1: ['Title Deed Transfer', 'OwnerCap handed to a new address'],
  // Orbital zone / Feral AI
  OZ1: ['Blind Spot', 'Orbital zone unscanned — dark patch in coverage'],
  OZ2: ['Tier Escalation', 'Feral AI threat level increased in zone'],
  FA1: ['Hive Surge', 'Feral AI activity spike — swarm forming'],
  FA2: ['Silent Zone', 'Active feral AI zone went dark — unknown status'],
  // Market manipulation
  MM1: ['Wash Cycle', 'Circular item flow between related wallets — no net economic purpose'],
  MM2: ['Price Cartel', 'Multiple assemblies set identical prices in coordinated window'],
  MM3: ['Supply Corner', 'Single wallet hoarding majority of an item type'],
}

// Anomaly type → frontier display name (fallback for when rule_id isn't available)
const TYPE_DISPLAY = {
  ORPHAN_OBJECT: 'Ghost Signal',
  RESURRECTION: 'Lazarus Event',
  STATE_GAP: 'Missing Trajectory',
  STUCK_OBJECT: 'Dead Drift',
  SUPPLY_DISCREPANCY: 'Phantom Ledger',
  UNEXPLAINED_DESTRUCTION: 'Vanishing Act',
  DUPLICATE_MINT: 'Double Stamp',
  NEGATIVE_BALANCE: 'Negative Mass',
  CONTRACT_STATE_MISMATCH: 'Forked State',
  FREE_GATE_JUMP: 'Toll Runner',
  FAILED_GATE_TRANSPORT: 'Gate Tax Lost',
  PHANTOM_ITEM_CHANGE: 'Shadow Inventory',
  UNEXPLAINED_OWNERSHIP_CHANGE: 'Silent Seizure',
  DUPLICATE_TRANSACTION: 'Event Storm',
  BLOCK_PROCESSING_GAP: 'Blind Spot',
  CHAIN_STATE_MISMATCH: 'Chain Divergence',
  DUPLICATE_KILLMAIL: 'Double Tap',
  THIRD_PARTY_KILL_REPORT: 'Witness Report',
  COORDINATED_BUYING: 'Convoy Forming',
  STATE_ROLLBACK: 'State Rollback',
  UNAUTHORIZED_STATE_MODIFICATION: 'Unauthorized Mod',
  ASSET_CONCENTRATION: 'Resource Baron',
  CONFIG_VERSION_CHANGE: 'Contract Tamper',
  INVENTORY_CONSERVATION_VIOLATION: 'Matter Violation',
  BOT_PATTERN: 'Drone Signature',
  RAPID_TRIBE_CHANGE: 'Drifter',
  ORPHANED_KILLMAIL: 'Orphaned Kill',
  GHOST_ENGAGEMENT: 'Phantom Kill',
  DEAD_ASSEMBLY: 'Derelict',
  VELOCITY_SPIKE: 'Gold Rush',
  VELOCITY_DROP: 'Market Silence',
  OWNERCAP_TRANSFER: 'Title Deed Transfer',
  OWNERCAP_DELEGATION: 'Title Deed Transfer',
  // Market manipulation
  WASH_TRADING: 'Wash Cycle',
  PRICE_FIXING: 'Price Cartel',
  ARTIFICIAL_SCARCITY: 'Supply Corner',
  // Orbital zone / Feral AI
  UNSCANNED_ZONE: 'Blind Spot',
  FERAL_AI_ESCALATION: 'Tier Escalation',
  FERAL_AI_SURGE: 'Hive Surge',
  FERAL_AI_BLACKOUT: 'Silent Zone',
  // Legacy/grouped map types
  POD_MISMATCH: 'Chain Divergence',
  CONTINUITY_BREAK: 'Ghost Signal',
  SEQUENCE_GAP: 'Blind Spot',
  ECONOMIC_ANOMALY: 'Phantom Ledger',
  ASSEMBLY_DRIFT: 'Forked State',
  KILLMAIL_ANOMALY: 'Double Tap',
  ORPHANED_INVENTORY: 'Matter Violation',
}

/**
 * Get frontier display name for an anomaly.
 * Tries rule_id first (most specific), falls back to anomaly_type.
 */
export function getDisplayName(anomaly) {
  if (anomaly.rule_id && RULE_DISPLAY[anomaly.rule_id]) {
    return RULE_DISPLAY[anomaly.rule_id][0]
  }
  const type = anomaly.anomaly_type || anomaly
  return TYPE_DISPLAY[type] || type.replace(/_/g, ' ')
}

/**
 * Get frontier display name from just an anomaly_type string.
 */
export function getTypeName(anomalyType) {
  return TYPE_DISPLAY[anomalyType] || anomalyType.replace(/_/g, ' ')
}

export { RULE_DISPLAY, TYPE_DISPLAY }
