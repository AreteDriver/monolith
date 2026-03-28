# Aegis Stack Demo Video — 3 Minutes

**Target**: Hackathon submission video (DeepSurge). Screen recording with voiceover.
**Covers**: WatchTower + Monolith + Discord Bot + Smart Assembly in-game (unified Aegis Stack demo)
**Tone**: Confident, concise, intelligence-briefing cadence. No hype words. No filler.
**Format**: 1920x1080 screen recording, record segments separately and edit together.
**Canonical script**: `witness/scripts/demo_video_script.md`. Keep in sync.

---

## TAB SETUP (do this BEFORE hitting record)

Open all tabs in this exact order, left-to-right.
Pre-scroll and zoom each tab to the exact state described.
Recording is done per-segment (stop/start between segments), edited together at the end.

```
TAB 1 — WatchTower Landing
  URL: https://watchtower-evefrontier.vercel.app/
  Zoom: 125%
  State: Scroll to top. "///" pulse visible. Wait for LIVE indicator.

TAB 2 — WatchTower Entity Search
  URL: https://watchtower-evefrontier.vercel.app/
  Zoom: 125%
  State: Click search bar, type "Specter" but DON'T select yet.
         You'll click the result during recording.

TAB 3 — WatchTower Entity Page (Specter)
  URL: https://watchtower-evefrontier.vercel.app/entity/Specter
  Zoom: 125%
  State: Scroll to show kill/death stats at top. Reputation section
         visible below fold. Pre-verify titles show.

TAB 4 — WatchTower Tactical
  URL: https://watchtower-evefrontier.vercel.app/entity/Specter
  Zoom: 125%
  State: Click "Tactical" tab. Let kill graph render. Pre-scroll to
         show HotzoneMap bars.

TAB 5 — WatchTower Dossier NFT
  URL: https://watchtower-evefrontier.vercel.app/dossier/Specter
  Zoom: 125%
  State: Show the 600x900 card render. Tier selection visible.
         Wallet connected and funded (~5 SUI min for mint + subscribe).

TAB 6 — WatchTower Account (Subscription + NEXUS)
  URL: https://watchtower-evefrontier.vercel.app/ (Account tab)
  Zoom: 125%
  State: Wallet connected. Tier badge visible. NEXUS webhook section loaded.

TAB 7 — Discord (#demo-alerts channel)
  URL: Discord app or browser — your server's #demo-alerts channel
  State: Channel empty / clean. Webhook created (URL copied for NEXUS demo).
         Bot online and visible in member list.

TAB 8 — Monolith Anomaly Feed
  URL: https://monolith-evefrontier.fly.dev/
  Zoom: 125%
  State: Scroll to show anomaly feed with recent detections.
         Pre-pick MNLT-20260328-0026 (GHOST_ENGAGEMENT, CRITICAL).

TAB 9 — Monolith Map (Command Center)
  URL: https://monolith-evefrontier.fly.dev/map
  Zoom: 125%
  State: Map should show 24K systems with anomaly heatmap.
         Pre-zoom to a cluster with anomalies. Reset button visible.

TAB 10 — Smart Assembly In-Game (OPTIONAL — server dependent)
  Source: Screenshot of deployed WatchTower Smart Assembly in EVE Frontier
  Zoom: 100%
  State: Show the assembly online in-game with name visible.
  FALLBACK: Suiscan screenshot of the subscription contract showing
            on-chain state + SubscriptionCap object.

TAB 11 — Sui Move Integration Code
  URL: Open contracts/sui/sources/integration_examples.move in VS Code
  Zoom: 125%
  State: Scroll to `assert_trusted()` function — the gate denial code.
         This is the money shot. Judges see: this changes gameplay.

TAB 12 — WatchTower Landing (closing shot)
  URL: https://watchtower-evefrontier.vercel.app/
  Zoom: 125%
  State: Same as Tab 1. This is for the closing numbers delivery.

TERMINAL — Keep a terminal ready (not a tab, use split or second monitor)
  State: Ready for NEXUS webhook curl command (pre-typed, don't hit enter yet).
```

**Segment recording order:** Record each segment separately, stop between them. Edit together in post. See RECORDING ORDER section below.

---

## PRE-RECORD CHECKLIST

**Infrastructure**
- [ ] All 12 tabs open and pre-scrolled per setup above
- [ ] Terminal ready with NEXUS curl command pre-typed
- [ ] Browser: dark mode, no bookmarks bar (`Ctrl+Shift+B`), no extensions visible
- [ ] Window: 1920x1080 on left half of ultrawide (`Super+Left` to snap)
- [ ] Browser zoom: 125% on all tabs (100% on Tab 10 if screenshot)
- [ ] Clear browser history/autocomplete (no embarrassing suggestions)
- [ ] Disable notifications: `gsettings set org.gnome.desktop.notifications show-banners false`
- [ ] Close Slack/other windows on recording half (Discord stays open for Tab 7)
- [ ] wf-recorder ready: `wf-recorder -g "0,0 1920x1080" -f ~/Videos/aegis-seg-N.mp4`

**Services**
- [ ] Verify WatchTower LIVE indicator shows green dot
- [ ] Verify Monolith map renders 24K systems (not black screen)
- [ ] Verify Specter entity has data (105 kills, 3 titles)
- [ ] Verify Social Assassin has data (67 kills, 67:1 KD)
- [ ] Pre-pick MNLT-20260328-0026 (GHOST_ENGAGEMENT) — verify detail + provenance works
- [ ] Verify hackathon mode active: `curl -s https://watchtower-evefrontier.fly.dev/api/account/hackathon-status | python3 -m json.tool`

**Wallet + Discord**
- [ ] Sui testnet wallet funded (~10 SUI from faucet)
- [ ] Wallet connected on WatchTower Account tab
- [ ] Discord `#demo-alerts` channel created with webhook URL copied
- [ ] Discord bot online in server (check member list)
- [ ] VS Code open to `integration_examples.move` (Tab 11)
- [ ] Smart Assembly screenshot/Suiscan fallback ready (Tab 10, optional)
- [ ] Practice each segment once before recording

---

## SEGMENT A — HOOK (0:00-0:12)

**[Screen: WatchTower landing page — "///" pulse, tagline visible]**

> "Every hackathon project reads the chain. Aegis Stack writes back to it. Two systems — WatchTower for behavioral intelligence, Monolith for anomaly detection — ingesting every Sui event and publishing reputation scores that Smart Assemblies enforce in the same transaction. This isn't a dashboard. It's infrastructure that changes on-chain behavior."

**Action**: Hold on landing page 3 seconds. Let the pulse animation breathe.

---

## SEGMENT B — ENTITY DOSSIER + REPUTATION (0:12-0:50)

**[Screen: Click search bar, type "Specter"]**

> "Search any entity by name or wallet address."

**Action**: Select Specter from dropdown. Entity page loads.

> "Full intelligence dossier. A hundred five confirmed kills. Behavioral fingerprint — temporal patterns, route analysis, OPSEC scoring. Everything computed from on-chain evidence. Nothing self-reported."

**Action**: Scroll slowly through entity page. Pause on:
1. Kill/death stats + danger rating (105 kills, 12 deaths)
2. Fingerprint card (threat level, kills/day)
3. Earned titles: "The Hunter", "The Marked", "The Reaper"

> "Earned titles are deterministic. Fifty kills earns 'The Reaper.' Thirty transits with zero combat earns 'The Ghost.' The chain writes the names."

**Action**: Scroll to reputation section.

> "Every entity scored zero to one hundred across six dimensions — Combat Honor, Target Diversity, Reciprocity, Consistency, Community, Restraint. These scores publish on-chain as Sui Move objects. A gate operator can enforce: deny docking if trust is below forty. Same transaction. No oracle delay."

---

## SEGMENT C — TACTICAL (0:50-1:05)

**Action**: Click "Tactical" tab.

> "Kill network graph — who kills whom, vendetta detection for mutual killers. Danger zones rank systems by kill density."

**Action**: Let kill graph render. Pause 2 seconds. Point at HotzoneMap bars.

> "System dossier — top attackers, victims, activity by hour. All derived from chain events."

---

## SEGMENT D — DOSSIER NFT MINT + WALLET (1:05-1:30)

**Action**: Navigate to dossier page. Show the 600x900 card render.

> "Dossier NFTs turn intelligence into tradeable on-chain assets. Three tiers — Intel is free, Classified costs half a SUI, Oracle costs two SUI. The Oracle tier references live shared registries. As reputation updates, the card updates. Trade the NFT, trade the live intelligence feed."

**Action**: Click mint button (Intel free or Classified 0.5 SUI). Approve in wallet popup. Show transaction confirmation.

> "That's a live Sui transaction. The card is in my wallet now."

**Action**: Open Sui wallet extension. Show the DossierCard NFT in your objects/assets list. Hold 3 seconds.

---

## SEGMENT E — SUBSCRIPTION + NEXUS WEBHOOK (1:30-1:55)

**Action**: Navigate to Account tab. Show wallet connected, tier badge.

> "Subscriptions work two ways — native SUI on-chain or Stripe for fiat. The on-chain subscription mints a SubscriptionCap — a proof-of-subscription NFT that any smart contract can verify atomically."

**Action**: If subscribing live, click subscribe → approve MoveCall → show SubscriptionCap in wallet.
**Alt**: Show existing subscription status if already subscribed.

**Action**: Switch to terminal. Run pre-typed NEXUS curl command:

```bash
curl -X POST https://watchtower-evefrontier.fly.dev/api/nexus/subscribe \
  -H "Content-Type: application/json" \
  -d '{"webhook_url":"DISCORD_WEBHOOK_URL","event_types":["killmail"]}'
```

> "The NEXUS API lets any builder register a webhook. Enriched chain events — killmails, anomalies, entity movements — pushed to your endpoint with HMAC signatures. Ten subscriptions, a thousand events per day at Spymaster tier."

**Action**: Show the API key and secret returned in the terminal output.

---

## SEGMENT F — DISCORD BOT (1:55-2:15)

**Action**: Switch to Discord `#demo-alerts` channel.

> "Twenty-one Discord slash commands. Full intelligence accessible without leaving comms."

**Action**: Type `/watchtower Specter` → show the embed response with fingerprint data, danger rating, titles.

**Action**: Type `/watch Specter` with webhook URL → show confirmation embed.

> "Standing watches. Set a target, get alerted on movement, kills, or proximity events. The Oracle loop evaluates every five minutes and fires Discord embeds."

**Action**: Type `/killfeed 3` → show latest kills embed.

**Action**: If a NEXUS webhook alert has fired to the channel, point at it:

> "And there's a NEXUS delivery — the webhook we just registered, already receiving enriched killmail data."

---

## SEGMENT G — MONOLITH TRANSITION + ANOMALY DETECTION (2:15-2:45)

**Action**: Switch to Monolith tab.

> "Monolith is the other half of the stack. Same chain data, different question. Not 'who is this entity' but 'is the economy intact.'"

**Action**: Scroll through anomaly feed.

> "Forty-two detection rules across twenty checkers. Supply discrepancies, duplicate mints, bot patterns, tribe-hopping spy signals, wallet concentration. Every rule is a pure function — events in, anomaly or nothing out."

**Action**: Click MNLT-20260328-0026 (GHOST_ENGAGEMENT, CRITICAL). Show the detail view.

> "Ghost engagement — a killmail victim with zero prior chain history. Phantom kill. Each detection carries a provenance chain — full audit trail back to the exact chain events. The Warden — an autonomous verifier — queries Sui and appends its own verdict. Take any entry, query the chain yourself. Zero trust required."

**Action**: Point at provenance entries and evidence JSON.

---

## SEGMENT H — HEATMAP (2:45-2:55)

**Action**: Navigate to the map view. Let Canvas2D heatmap render.

> "Twenty-four thousand five hundred systems at sixty frames per second. Anomaly density by region. Click any system for the detection breakdown."

**Action**: Pan/zoom briefly. Click a highlighted system.

---

## SEGMENT I — SMART ASSEMBLY + MOVE CODE (2:55-3:15)

**Action**: Switch to Tab 10 (in-game screenshot or Suiscan). **OPTIONAL — skip if server down.**

> "This is a WatchTower Smart Assembly deployed in-game. A revenue-generating intelligence node — every deployment is both a service point and a billboard."

**Action**: Hold on in-game screenshot 3 seconds. Switch to Tab 11 (VS Code with Move code).

> "Here's why this matters. Any gate operator imports our registry. `assert_trusted` — entity address, minimum trust score, shared reputation registry. The check happens atomically in the same transaction as the gate decision. No off-chain lookup. No bridge. No latency. Reputation scores that change docking permissions in real time."

**Action**: Highlight the `assert_trusted()` function. Pause on it 3 seconds. Judges need to read it.

---

## SEGMENT J — THE LOOP + CLOSE (3:15-3:30)

**Action**: Switch back to WatchTower landing page.

> "Here's the loop no other project closes. Chain events flow in. WatchTower fingerprints behavior and scores reputation. Scores publish on-chain. Smart Assemblies read those scores in the same transaction they make access decisions. Player behavior adapts. New events flow in. The cycle tightens."

**Action**: Brief pause.

> "Sixteen hundred forty tests. Forty-two detection rules with full provenance chains. Six Sui Move modules. Over fifty-four thousand chain events ingested. Seven hundred twenty-one anomalies detected. Thirteen thousand entities fingerprinted. Both systems live in production. Solo-built. Aegis Stack."

**Action**: Hold on landing page. Let the "///" pulse breathe. End recording.

---

## RECORDING COMMANDS

```bash
# Test capture first (5 seconds)
timeout 5 wf-recorder -g "0,0 1920x1080" -f ~/Videos/test-capture.mp4
xdg-open ~/Videos/test-capture.mp4

# Record each segment separately (replace N with segment letter)
wf-recorder -g "0,0 1920x1080" -f ~/Videos/aegis-seg-A.mp4
# Stop: Ctrl+C between segments

# Record with microphone (if doing live narration per segment)
wf-recorder -g "0,0 1920x1080" --audio -f ~/Videos/aegis-seg-A.mp4

# Record voiceover separately (alternative — record all VO in one pass)
ffmpeg -f pulse -i default -ac 1 -ar 44100 ~/Videos/voiceover.mp3
# Stop: Ctrl+C
```

## POST-PRODUCTION (ffmpeg)

```bash
# Trim dead air from each segment (adjust timestamps per file)
for seg in A B C D E F G H I J; do
  ffmpeg -i ~/Videos/aegis-seg-${seg}.mp4 -ss 1 -c copy ~/Videos/aegis-trim-${seg}.mp4
done

# Concatenate all trimmed segments
# 1. Create file list
for seg in A B C D E F G H I J; do
  echo "file 'aegis-trim-${seg}.mp4'" >> ~/Videos/concat-list.txt
done
# 2. Merge
ffmpeg -f concat -safe 0 -i ~/Videos/concat-list.txt -c copy ~/Videos/aegis-demo-joined.mp4

# Add voiceover (if recorded separately)
ffmpeg -i ~/Videos/aegis-demo-joined.mp4 -i ~/Videos/voiceover.mp3 \
  -c:v copy -c:a aac -map 0:v -map 1:a ~/Videos/aegis-demo-final.mp4

# Compress for upload (<100MB for YouTube)
ffmpeg -i ~/Videos/aegis-demo-final.mp4 \
  -c:v libx264 -crf 23 -preset medium \
  -c:a aac -b:a 128k \
  ~/Videos/aegis-demo-upload.mp4

ls -lh ~/Videos/aegis-demo-upload.mp4
```

## RECORDING TIPS

- **Pace**: ~150 words/minute. Slightly slower than conversational.
- **Mouse**: Move deliberately. No jittery cursor. Hover on what you're discussing.
- **Pauses**: 1-second pause between segments. Let visuals register.
- **Segments**: Record each separately. Stop between them. Retake any that feel off.
- **Segment I is the money shot**: Linger on the Move code. Let judges read `assert_trusted()`.
- **Audio**: Record voiceover per-segment for easiest editing. Or do one VO pass in post.
- **Wallet shots**: After every on-chain action (mint, subscribe), show the wallet.
- **Discord**: Have the channel visible. If a webhook fires during recording, capture it.
- **If over 3:30**: Trim Segment C (Tactical) to 5 seconds. Cut the system click.
- **If under 2:30**: Expand Segment I (Smart Assembly) with `full_security_check()` example.

## RECORDING ORDER (cheat sheet)

Record in this order. Stop/start between each. Edit together in post.

```
SEG A — WatchTower `/` — hold 3s on "///" pulse
SEG B — Search "Specter" -> entity page -> scroll stats/fingerprint/titles/reputation
SEG C — Click "Tactical" -> kill graph -> hotzone bars
SEG D — Dossier page -> show card -> MINT (approve in wallet) -> open wallet -> show NFT
SEG E — Account tab (subscription) -> terminal: NEXUS curl -> show API key returned
SEG F — Discord: /watchtower Specter -> /watch Specter -> /killfeed 3 -> webhook alert
SEG G — Monolith landing -> anomaly feed -> click CRITICAL -> show evidence + provenance
SEG H — Map view -> pan/zoom -> click system
SEG I — SA screenshot (optional) -> VS Code: assert_trusted() (hold 3s)
SEG J — WatchTower landing -> deliver numbers -> hold on "///" -> end
```

## NUMBERS TO CITE (verify from live /api/health BEFORE recording)

| Metric | Value | Say As | Source |
|--------|-------|--------|--------|
| Tests | 1,640 | "sixteen hundred forty" | pytest (1,033 witness + 607 monolith) |
| Detection rules | 42 | "forty-two" | monolith checkers |
| Checkers | 20 | "twenty" | monolith engine |
| Chain events | 54,237 | "over fifty-four thousand" | monolith /api/health |
| Anomalies detected | 721 | "seven hundred twenty-one" | monolith /api/health |
| State transitions | 295,828 | "nearly three hundred thousand" | monolith /api/health |
| Objects tracked | 861 | "over eight hundred" | monolith /api/health |
| Systems mapped | 24,502 | "twenty-four thousand five hundred" | static data |
| Entities indexed | 13,161 | "thirteen thousand" | watchtower /api/health |
| Killmails analyzed | 449 | "over four hundred" | watchtower /api/health |
| Story feed items | 750 | "seven hundred fifty" | watchtower /api/health |
| Sui Move modules | 6 | "six" | deployed contracts |
| Discord commands | 21 | "twenty-one" | bot registration |
| Live deployments | 5 | "five" | Fly.io x2 + Vercel x3 |
| Hackathon mode | Active | "expires May first" | /api/account/hackathon-status |

**Verify before recording**: `curl -s https://monolith-evefrontier.fly.dev/api/health | python3 -m json.tool` and `curl -s https://watchtower-evefrontier.fly.dev/api/health | python3 -m json.tool` — numbers will have grown by recording time.

## BACKUP: API DEMO (if frontend has issues)

```bash
# WatchTower
curl -s https://watchtower-evefrontier.fly.dev/api/health | python3 -m json.tool
curl -s 'https://watchtower-evefrontier.fly.dev/api/search?q=Specter' | python3 -m json.tool
curl -s https://watchtower-evefrontier.fly.dev/api/entity/2112077764 | python3 -m json.tool
curl -s https://watchtower-evefrontier.fly.dev/api/entity/2112077764/fingerprint | python3 -m json.tool
curl -s https://watchtower-evefrontier.fly.dev/api/feed?limit=5 | python3 -m json.tool
curl -s https://watchtower-evefrontier.fly.dev/api/account/hackathon-status | python3 -m json.tool

# Monolith
curl -s https://monolith-evefrontier.fly.dev/api/health | python3 -m json.tool
curl -s 'https://monolith-evefrontier.fly.dev/api/anomalies?limit=5&severity=CRITICAL' | python3 -m json.tool
curl -s https://monolith-evefrontier.fly.dev/api/stats | python3 -m json.tool

# NEXUS webhook subscribe (use your Discord webhook URL)
curl -X POST https://watchtower-evefrontier.fly.dev/api/nexus/subscribe \
  -H "Content-Type: application/json" \
  -d '{"webhook_url":"YOUR_DISCORD_WEBHOOK_URL","event_types":["killmail"]}'
```

## DEMO ENTITIES (pre-scouted 2026-03-28)

| Entity | ID | Kills | Deaths | Titles | Use For |
|--------|----|-------|--------|--------|---------|
| **Specter** | 2112077764 | 105 | 12 | Hunter, Marked, Reaper | Primary demo — in script |
| **Social Assassin** | 2112077449 | 67 | 1 | Hunter, Reaper | Alt demo — 67:1 KD, OPSEC 25/100 |

## DEMO ANOMALIES (pre-picked 2026-03-28)

| ID | Type | Severity | Rule | Good Because |
|----|------|----------|------|--------------|
| MNLT-20260328-0026 | GHOST_ENGAGEMENT | CRITICAL | ES2 | Phantom victim, zero chain history — dramatic |
| MNLT-20260328-0009 | UNAUTHORIZED_STATE_MODIFICATION | HIGH | OV2 | Version delta 967K — impressive number |

## RE-ENABLE AFTER RECORDING

```bash
gsettings set org.gnome.desktop.notifications show-banners true
```

## SA DEPLOYMENT NOTES (OPTIONAL — server dependent)

If EVE Frontier server (Stillness) comes back online before recording:
1. Deploy a WatchTower Smart Assembly in-game
2. Screenshot the assembly ONLINE with name visible
3. Get the Suiscan link for the on-chain object
4. Note the system name for the voiceover
5. If possible, capture a short clip of a player interacting with it
6. Update Tab 10 with the actual screenshot before recording

**FALLBACK** (server down): Use Suiscan screenshot of the deployed contract:
`https://suiscan.xyz/testnet/object/0x3ca7e3af5bf5b072157d02534f5e4013cf11a12b79385c270d97de480e7b7dca`
Show the 6 modules (reputation, threat_registry, dossier, subscription, titles, integration_examples).
