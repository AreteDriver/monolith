# Next Session TODO — Monolith Hackathon Sprint

**Deadline: March 31, 2026 (5 days)**
**Last session: 2026-03-26**

## Must Ship

- [ ] **Demo video** — Record walkthrough of Monolith map with WatchTower overlays (kills, threat, assemblies). Show click-to-select, layer toggles, threat feed integration. This is the visual hook
- [ ] **Submission writeup** — Aegis Stack story: Monolith (detection) + WatchTower (intelligence) + Frontier Tribe OS (operations). Emphasize: live production deployments, not mockups. 774+ WT tests, 607 Monolith tests, 24K systems mapped, dual payment rails
- [ ] **Test `grant_dossier.py` with live wallet** — Run `python scripts/grant_dossier.py <entity> pilot "Name" 2 <recipient> --dry-run` first, then real. Confirm admin cap works before comping judges

## Should Do

- [ ] **Verify Vercel auto-deploy** — WatchTower push (MonolithMapLink + vuln fixes) should have triggered Vercel deploy. Check `watchtower-evefrontier.vercel.app` looks correct
- [ ] **Check dependabot alerts cleared** — picomatch overrides pushed, GitHub should have re-scanned. If 2 alerts persist, manually dismiss
- [ ] **Threat score labels** — deployed but not visually verified. Open `aegismonolith.xyz/map`, zoom to 1.5x+, confirm dark pill backgrounds render clean

## Nice to Have

- [ ] Delete the 3 orphaned component files from WatchTower (HotzoneMap.tsx, ActivityMap.tsx, AssemblyMap.tsx) — imports removed but files still on disk
- [ ] Monolith Vercel redeploy from `frontend/` if latest push didn't auto-trigger
