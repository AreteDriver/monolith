# Aegis Stack — Demo Screen Setup Guide

## Your Display

- **Monitor**: 3840x1080 (ultrawide via xrandr DisplayPort-0)
- **Recording area**: Left half — 1920x1080 (standard 1080p)
- **Browser**: Google Chrome (default)
- **Recorder**: wf-recorder 0.4.1 (Wayland) + ffmpeg 6.1.1

---

## Step 1: Verify Live Backends

Both backends must be up. The live deployments already have real data — no seeding needed.

```bash
# Check both backends
curl -s https://watchtower-evefrontier.fly.dev/api/health | python3 -m json.tool
curl -s https://monolith-evefrontier.fly.dev/api/health | python3 -m json.tool

# If either is down, restart on Fly.io
/home/arete/.fly/bin/flyctl machine list -a watchtower-evefrontier
/home/arete/.fly/bin/flyctl machine start <machine-id> -a watchtower-evefrontier

/home/arete/.fly/bin/flyctl machine list -a monolith-evefrontier
/home/arete/.fly/bin/flyctl machine start <machine-id> -a monolith-evefrontier
```

**Expected live data (verified 2026-03-27):**

| Backend | Key Metric | Value |
|---------|-----------|-------|
| WatchTower | Entities indexed | 12,600 |
| WatchTower | Killmails | 486 |
| WatchTower | Story feed items | 1,307 |
| Monolith | Chain events | 47,102 |
| Monolith | Anomalies | 660 |
| Monolith | State transitions | 295,296 |
| Monolith | Objects tracked | 826 |

---

## Step 2: Browser Setup

### Launch Chrome at Recording Size
```bash
# Snap to left half of ultrawide
google-chrome --window-size=1920,1080 --window-position=0,0 \
  "https://watchtower-evefrontier.vercel.app/" &
```
Or: open Chrome, press `Super+Left` to snap to left 1920x1080.

### Chrome Settings
1. **Hide bookmarks bar**: `Ctrl+Shift+B`
2. **Zoom**: Set to **125%** on all tabs (`Ctrl+Shift++`)
3. **DevTools**: Closed (`F12` to toggle)
4. **Extensions**: Hide icons — right-click each > "Unpin from toolbar"
5. **Incognito** (optional): `Ctrl+Shift+N` for clean toolbar

### Open 9 Tabs (exact order — see DEMO-VIDEO-SCRIPT.md for full setup)

| Tab | URL | Pre-State |
|-----|-----|-----------|
| 1 | `watchtower-evefrontier.vercel.app/` | Landing, LIVE indicator visible |
| 2 | `watchtower-evefrontier.vercel.app/` | Search bar, "Specter" typed but not selected |
| 3 | `watchtower-evefrontier.vercel.app/entity/Specter` | Entity page loaded, stats visible |
| 4 | `watchtower-evefrontier.vercel.app/entity/Specter` | Tactical tab, kill graph rendered |
| 5 | `watchtower-evefrontier.vercel.app/` | Feed & Rankings tab |
| 6 | `watchtower-evefrontier.vercel.app/dossier/Specter` | Dossier card visible |
| 7 | `monolith-evefrontier.fly.dev/` | Landing + anomaly feed |
| 8 | `monolith-evefrontier.fly.dev/map` | Map with 24K systems rendered |
| 9 | `watchtower-evefrontier.vercel.app/` | Landing (closing shot) |

### Pre-load Verification
Visit each tab once before recording so everything is cached and rendering:

- [ ] Tab 1: WatchTower LIVE indicator shows green
- [ ] Tab 3: Specter has kills, reputation bars, earned titles
- [ ] Tab 4: Kill graph renders (may take 2-3 seconds)
- [ ] Tab 6: Dossier card image loads (600x900 render)
- [ ] Tab 7: Monolith stats grid shows non-zero numbers
- [ ] Tab 8: Map shows 24K systems (not black screen — give it 5 seconds)

---

## Step 3: Pre-Pick an Anomaly

Before recording, find a good CRITICAL or HIGH anomaly on Monolith (Tab 7):

1. Go to `monolith-evefrontier.fly.dev/anomalies`
2. Filter by CRITICAL severity
3. Click into one — verify it has:
   - Full evidence block (transaction hash, object ID)
   - A system name (not just an ID)
   - Generate Report works (click it, verify narration appears)
4. Note the anomaly ID — you'll navigate to it during Scene 8
5. Use browser Back to return to the feed

---

## Step 4: Desktop Cleanup

```bash
# Disable notifications
gsettings set org.gnome.desktop.notifications show-banners false

# Close all other windows on left half
# Set dark wallpaper (dark-themed apps won't clash if edges show)
```

---

## Step 5: Test Recording

```bash
# Quick 5-second test to verify capture area
timeout 5 wf-recorder -g "0,0 1920x1080" -f ~/Videos/test-capture.mp4

# Verify it captured the right area
xdg-open ~/Videos/test-capture.mp4
```

If geometry is wrong, check your display:
```bash
xrandr | grep -E 'connected|current'
# Adjust geometry offset if needed (e.g., "0,0" vs "1920,0")
```

---

## Step 6: Record

```bash
# Screen only (add voiceover later — recommended)
wf-recorder -g "0,0 1920x1080" -f ~/Videos/aegis-demo-raw.mp4
# Stop: Ctrl+C

# OR screen + live microphone
wf-recorder -g "0,0 1920x1080" --audio -f ~/Videos/aegis-demo-raw.mp4
```

Follow the scene sequence in `DEMO-VIDEO-SCRIPT.md`. Ctrl+Tab through tabs 1-9. One direction.

---

## Step 7: Post-Production

```bash
# Record separate voiceover (if not done live)
ffmpeg -f pulse -i default -ac 1 -ar 44100 ~/Videos/voiceover.mp3
# Stop: Ctrl+C

# Trim dead air
ffmpeg -i ~/Videos/aegis-demo-raw.mp4 -ss 2 -to 185 -c copy ~/Videos/aegis-demo-trimmed.mp4

# Merge video + voiceover
ffmpeg -i ~/Videos/aegis-demo-trimmed.mp4 -i ~/Videos/voiceover.mp3 \
  -c:v copy -c:a aac -map 0:v -map 1:a ~/Videos/aegis-demo-final.mp4

# Compress for YouTube upload (<100MB)
ffmpeg -i ~/Videos/aegis-demo-final.mp4 \
  -c:v libx264 -crf 23 -preset medium \
  -c:a aac -b:a 128k \
  ~/Videos/aegis-demo-upload.mp4

ls -lh ~/Videos/aegis-demo-upload.mp4
```

---

## Step 8: Cleanup

```bash
# Re-enable notifications
gsettings set org.gnome.desktop.notifications show-banners true

# Upload to YouTube (unlisted first)
# Add URL to witness/docs/HACKATHON_SUBMISSION.md
```

---

## Quick Reference

| Action | Command / Key |
|--------|--------------|
| Start recording | `wf-recorder -g "0,0 1920x1080" -f ~/Videos/aegis-demo-raw.mp4` |
| Stop recording | `Ctrl+C` |
| Hide bookmarks | `Ctrl+Shift+B` |
| Set zoom 125% | `Ctrl+Shift++` (repeat) |
| Reset zoom | `Ctrl+0` |
| Fullscreen | `F11` |
| Next tab | `Ctrl+Tab` |
| Disable notifs | `gsettings set org.gnome.desktop.notifications show-banners false` |
| Trim video | `ffmpeg -i in.mp4 -ss START -to END -c copy out.mp4` |
| Play video | `xdg-open ~/Videos/aegis-demo-raw.mp4` |
