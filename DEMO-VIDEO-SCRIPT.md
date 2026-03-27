# Aegis Stack Demo Video — 3 Minutes

**Target**: Hackathon submission video (DeepSurge). Screen recording with voiceover.
**Covers**: WatchTower + Monolith (unified Aegis Stack demo)
**Tone**: Confident, concise, intelligence-briefing cadence. No hype words. No filler.
**Format**: 1920x1080 screen recording, separate voiceover track preferred.
**Canonical script**: This file mirrors `witness/scripts/demo_video_script.md`. Keep in sync.

---

## TAB SETUP (do this BEFORE hitting record)

Open 9 Chrome tabs in this exact order, left-to-right.
Pre-scroll and zoom each tab to the exact state described.
During recording, Ctrl+Tab through them like a slideshow. One direction. Never go backwards.

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

TAB 5 — WatchTower Feed & Rankings
  URL: https://watchtower-evefrontier.vercel.app/
  Zoom: 125%
  State: Navigate to Feed tab. Scroll to show story feed + leaderboard.

TAB 6 — WatchTower Dossier NFT
  URL: https://watchtower-evefrontier.vercel.app/dossier/Specter
  Zoom: 125%
  State: Show the 600x900 card render. Tier selection visible.

TAB 7 — Monolith Landing + Anomaly Feed
  URL: https://monolith-evefrontier.fly.dev/
  Zoom: 125%
  State: Scroll to show anomaly feed with recent detections.
         Pre-identify one CRITICAL anomaly to click during recording.

TAB 8 — Monolith Map (Command Center)
  URL: https://monolith-evefrontier.fly.dev/map
  Zoom: 125%
  State: Map should show 24K systems with anomaly heatmap + WatchTower overlay.
         Pre-zoom to a cluster with anomalies. Reset button visible.

TAB 9 — WatchTower Landing (closing shot)
  URL: https://watchtower-evefrontier.vercel.app/
  Zoom: 125%
  State: Same as Tab 1. This is for the closing numbers delivery.
```

**Flow during recording:** Tab 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9. One direction. Never go backwards.

---

## PRE-RECORD CHECKLIST

- [ ] All 9 tabs open and pre-scrolled per setup above
- [ ] Browser: dark mode, no bookmarks bar (`Ctrl+Shift+B`), no extensions visible
- [ ] Window: 1920x1080 on left half of ultrawide (`Super+Left` to snap)
- [ ] Browser zoom: 125% on all tabs
- [ ] Verify WatchTower LIVE indicator shows green dot
- [ ] Verify Monolith map renders 24K systems (not black screen)
- [ ] Verify Specter entity has data (kills, reputation, titles)
- [ ] Pre-pick one CRITICAL anomaly on Monolith — verify detail + report generation works
- [ ] Clear browser history/autocomplete (no embarrassing suggestions)
- [ ] Disable notifications: `gsettings set org.gnome.desktop.notifications show-banners false`
- [ ] Close Slack/Discord/other windows on recording half
- [ ] wf-recorder ready: `wf-recorder -g "0,0 1920x1080" -f ~/Videos/aegis-demo-raw.mp4`
- [ ] Practice the tab-through sequence twice before recording
- [ ] Have backup curl commands ready in terminal (see bottom of script)

---

## SCENE 1 — HOOK (0:00-0:10)

**[Screen: WatchTower landing page — "///" pulse, tagline visible]**

> "Aegis Stack is the immune system of EVE Frontier. Two systems — WatchTower for behavioral intelligence, Monolith for anomaly detection — reading every event from the Sui blockchain and turning raw chain data into actionable signal."

**Action**: Hold on landing page 3 seconds. Let the pulse animation breathe.

---

## SCENE 2 — ENTITY DOSSIER (0:10-0:35)

**[Screen: Click search bar, type "Specter"]**

> "Search any entity by name or wallet address."

**Action**: Select Specter from dropdown. Entity page loads.

> "Full intelligence dossier. Confirmed kills, deaths, chain events. Behavioral fingerprint — temporal patterns, route analysis, OPSEC scoring. Everything computed from on-chain evidence. Nothing self-reported."

**Action**: Scroll slowly through entity page. Pause on:
1. Kill/death stats + danger rating
2. Fingerprint card (threat level, kills/day)
3. Earned titles: "The Hunter", "The Marked", "The Reaper"

> "Earned titles are deterministic. Fifty kills earns 'The Reaper.' Thirty transits with zero combat earns 'The Ghost.' The chain writes the names."

---

## SCENE 3 — REPUTATION (0:35-0:55)

**Action**: Scroll to reputation section on entity page.

> "Every entity scored zero to one hundred across six dimensions — Combat Honor, Target Diversity, Reciprocity, Consistency, Community, Restraint."

**Action**: Point at each dimension bar. Pause on the overall trust score.

> "These scores aren't cosmetic. They publish on-chain as Sui Move objects. A gate operator can enforce: deny docking if trust is below forty. The reputation check and the gate check happen in the same transaction. No oracle delay. No stale data."

**Action**: Briefly show the on-chain badge / "Published on Sui" indicator if visible.

---

## SCENE 4 — TACTICAL (0:55-1:15)

**Action**: Click "Tactical" tab.

> "Kill network graph — who kills whom, with vendetta detection for mutual killers."

**Action**: Let kill graph render. Pause 2 seconds.

> "Danger zones rank systems by kill density. Color-coded threat levels."

**Action**: Point at HotzoneMap bars. Click top system.

> "System dossier — top attackers, victims, activity by hour. All from chain events."

**Action**: Scroll system dossier briefly, navigate back.

---

## SCENE 5 — STORY FEED + LIVE DATA (1:15-1:30)

**Action**: Click "Feed & Rankings" tab.

> "WatchTower auto-generates intelligence stories. Kill streaks, new entity sightings, skirmish alerts — derived from event clustering, not AI. The leaderboard tracks top killers, most deaths, most traveled."

**Action**: Scroll feed briefly. Glance at leaderboard. Click a name to show it links to dossier.

---

## SCENE 6 — DOSSIER NFTs (1:30-1:45)

**Action**: Navigate to dossier page.

> "Dossier NFTs turn intelligence into tradeable on-chain assets. Three tiers — Intel is free, Classified costs half a SUI, Oracle costs two SUI. The Oracle tier auto-updates. Trade the card, trade the live intelligence feed. The card never goes stale."

**Action**: Show the 600x900 card render with threat bars, reputation stats, titles. Point at tier selection if visible.

---

## SCENE 7 — MONOLITH TRANSITION (1:45-1:55)

**Action**: Switch to Monolith tab.

> "Monolith is the other half of the stack. Same chain data, different question. Not 'who is this entity' but 'is the economy intact.'"

**Action**: Let Monolith landing page load. Show the anomaly feed with live stats.

---

## SCENE 8 — ANOMALY DETECTION + PROVENANCE (1:55-2:25)

**Action**: Scroll through anomaly feed.

> "Thirty-nine detection rules across eighteen checkers. Every rule is a pure function — events and state in, anomaly or nothing out. Supply discrepancies, duplicate mints, bot patterns, tribe-hopping spy signals, dead infrastructure mapping, wallet concentration."

**Action**: Click into a specific anomaly. Show the detail view.

> "Each detection carries a provenance chain — a full audit trail linking the detection back to the exact chain events that produced it. Source type, transaction hash, timestamp, derivation logic. The Warden — an autonomous verification system — queries the Sui chain and appends its own provenance when it confirms or dismisses."

**Action**: Point at the provenance entries in the detail view. Highlight source_type and derivation fields.

> "Take any provenance entry, query the chain yourself, reproduce the detection. Zero trust required. Cryptographic proof all the way down."

**Action**: Point at the severity badge and Warden status (VERIFIED/DISMISSED).

---

## SCENE 9 — HEATMAP (2:25-2:40)

**Action**: Navigate to the map view. Let Canvas2D heatmap render.

> "Twenty-four thousand five hundred systems rendered at sixty frames per second. Canvas2D scanline heatmap with WatchTower intelligence overlay — kill networks, threat zones, assembly states. Click any system for the detection breakdown."

**Action**: Pan/zoom the map briefly. Click a highlighted system. Show the threat feed filtering on the right.

---

## SCENE 10 — THE LOOP (2:40-2:50)

**Action**: Switch back to WatchTower tab. Show the landing page.

> "Here's the loop no other project closes. Chain events flow in. WatchTower fingerprints behavior and scores reputation. Scores publish on-chain. Smart Assemblies read those scores in the same transaction they make access control decisions. Player behavior adapts. New chain events flow in. The cycle tightens."

**Action**: Scroll to show the Aegis ecosystem section if visible.

> "Monolith's public API and webhooks give CCP a real-time economic audit layer. Bot detection, supply integrity, state anomalies — consumable without building it themselves."

---

## SCENE 11 — NUMBERS + CLOSE (2:50-3:00)

**[Screen: Hold on WatchTower landing page]**

> "Fifteen hundred sixty tests. Thirty-nine detection rules — each with full provenance chains. A hundred sixty-seven API endpoints. Four Sui Move modules deployed. Forty-seven thousand chain events. Six hundred sixty anomalies detected with auditable evidence trails. Nearly three hundred thousand state transitions tracked. Both systems live in production. Solo-built. Aegis Stack — the immune system of EVE Frontier."

**Action**: Hold on landing page. Let the "///" pulse breathe. End recording.

---

## RECORDING COMMANDS

```bash
# Start recording (left half of 3840x1080 ultrawide)
wf-recorder -g "0,0 1920x1080" -f ~/Videos/aegis-demo-raw.mp4

# Stop: Ctrl+C

# Test capture first (5 seconds)
timeout 5 wf-recorder -g "0,0 1920x1080" -f ~/Videos/test-capture.mp4
xdg-open ~/Videos/test-capture.mp4

# Record with microphone (live narration)
wf-recorder -g "0,0 1920x1080" --audio -f ~/Videos/aegis-demo-raw.mp4

# Record voiceover separately (recommended)
ffmpeg -f pulse -i default -ac 1 -ar 44100 ~/Videos/voiceover.mp3
# Stop: Ctrl+C
```

## POST-PRODUCTION (ffmpeg)

```bash
# Trim dead air (adjust timestamps)
ffmpeg -i ~/Videos/aegis-demo-raw.mp4 -ss 2 -to 185 -c copy ~/Videos/aegis-demo-trimmed.mp4

# Merge video + separate voiceover
ffmpeg -i ~/Videos/aegis-demo-trimmed.mp4 -i ~/Videos/voiceover.mp3 \
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
- **Pauses**: 1-second pause between scenes. Let visuals register.
- **Transitions**: Tab switch between WatchTower and Monolith should feel natural.
- **Audio**: Record voiceover SEPARATELY for cleaner mix. Or narrate live.
- **If over 3 min**: Cut Scene 5 (Feed) and trim Scene 9 (Heatmap to 5 seconds).
- **If under 2:30**: Expand Scene 3 (Reputation) with a second entity comparison.

## CLICK SEQUENCE (cheat sheet)

```
1. WatchTower `/` — hold 3s
2. Search "Specter" -> click -> entity page
3. Scroll: stats -> fingerprint -> titles -> reputation
4. Click "Tactical" tab -> kill graph -> hotzone bars -> click system
5. Back -> "Feed & Rankings" -> scroll feed -> glance leaderboard
6. Dossier tab -> show card render -> tier selection
7. Switch to Monolith tab
8. Anomaly feed -> click anomaly detail -> show provenance chain
9. Map view -> pan/zoom -> click system -> threat feed filters
10. Back to WatchTower tab -> landing page
11. Hold on "///" — deliver closing numbers — end
```

## NUMBERS TO CITE (verified 2026-03-27 from live /api/health)

| Metric | Value | Say As | Source |
|--------|-------|--------|--------|
| Tests | 1,560+ | "fifteen hundred sixty" | pytest (774+591+195) |
| Detection rules | 39 | "thirty-nine" | monolith CLAUDE.md |
| Checkers | 18 | "eighteen" | monolith CLAUDE.md |
| API endpoints | 167 | "a hundred sixty-seven" | route counts |
| Chain events | 47,102 | "forty-seven thousand" | monolith /api/health |
| Anomalies detected | 660 | "six hundred sixty" | monolith /api/health |
| State transitions | 295,296 | "nearly three hundred thousand" | monolith /api/health |
| Objects tracked | 826 | "over eight hundred" | monolith /api/health |
| Systems mapped | 24,502 | "twenty-four thousand five hundred" | static data |
| Entities indexed | 12,600 | "over twelve thousand" | watchtower /api/health |
| Killmails analyzed | 486 | "nearly five hundred" | watchtower /api/health |
| Story feed items | 1,307 | "over thirteen hundred" | watchtower /api/health |
| Bug reports auto-filed | 43 | "forty-three" | monolith /api/health |
| Sui Move modules | 4 | "four" | deployed contracts |
| Discord commands | 15 | "fifteen" | bot registration |
| On-chain transactions | 68+ | "sixty-eight" | sui explorer |
| Live deployments | 5 | "five" | Fly.io x2 + Vercel x3 |

## BACKUP: API DEMO (if frontend has issues)

```bash
# WatchTower
curl -s https://watchtower-evefrontier.fly.dev/api/health | python3 -m json.tool
curl -s 'https://watchtower-evefrontier.fly.dev/api/search?q=Specter' | python3 -m json.tool
curl -s https://watchtower-evefrontier.fly.dev/api/leaderboard/top_killers | python3 -m json.tool
curl -s https://watchtower-evefrontier.fly.dev/api/hotzones | python3 -m json.tool

# Monolith
curl -s https://monolith-evefrontier.fly.dev/api/health | python3 -m json.tool
curl -s 'https://monolith-evefrontier.fly.dev/api/anomalies?limit=5' | python3 -m json.tool
curl -s https://monolith-evefrontier.fly.dev/api/stats | python3 -m json.tool
```

## RE-ENABLE AFTER RECORDING

```bash
gsettings set org.gnome.desktop.notifications show-banners true
```
