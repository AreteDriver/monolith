# ARCHIVED — monolith

**Archived**: 2026-04-25
**Last version**: v0.5.0
**Tests at archive**: 728 (84% coverage, CI gate 80%)
**Live deployment at archive**: `monolith-evefrontier.fly.dev` (suspended 2026-04-25)

---

## Why archived

Built for the EVE Frontier × Sui hackathon (Mar 11 – Apr 19, 2026).
Hackathon concluded with no placement. Owner is not continuing to play
or support EVE Frontier, so this codebase is no longer maintained.

This is a deliberate stop, not a pause. The energy is being redirected
to general AI-infrastructure work (drift-monitor, arete-evals) where
the portfolio signal compounds outside a single game ecosystem.

## What was preserved

The shipped code, commit history, and 728-test suite stay in this repo
as evidence of work delivered under a real deadline. Issues, PRs, and
deployment logs remain accessible.

## What was extracted

Five architectural patterns were extracted into
`animus/packages/forge/docs/patterns/detection-framework-monolith.md`
before archive:

1. **Typed `Anomaly` + `ProvenanceEntry` schema** — the audit-trail
   shape that survives outside Frontier. From `backend/detection/base.py`.
2. **Deterministic 4-dimension rubric for LLM-output evaluation** — the
   headline reusable IP. Factual grounding, severity alignment,
   actionability, hallucination flag. From `eval/narration_eval.py`.
3. **DB-backed dedup that survives process restarts** — JOIN-based
   between `filed_issues` and `anomalies`. From
   `backend/alerts/github_issues.py` + `backend/detection/engine.py`.
4. **Severity/type-filtered webhook subscription dispatch** — two
   allowlist filters, async dispatch, per-subscription error isolation.
   From `backend/api/subscriptions.py` +
   `backend/alerts/subscription_dispatch.py`.
5. **Detection-cycle telemetry as a first-class table** — operational
   data co-located with application data for P50/P95 latency queries
   and drift detection on detector behavior. From `backend/db/database.py`.

The 36 detection rules, the 3D galaxy map, the chain-poll loops, and
the Warden are NOT extracted — they are tightly coupled to Sui chain
event shapes and EVE Frontier object semantics, and don't generalize.

## What you can still do here

- Read the code, the tests, and the commit history.
- Read the original [README.md](./README.md) and [CLAUDE.md](./CLAUDE.md)
  for the as-built architecture.
- Resurrect the Fly app from `fly.toml` if needed (machine was
  suspended, not destroyed; config and image are intact).

## What is no longer happening

- No new features.
- No bug fixes.
- No dependency updates (Dependabot PRs will not be merged).
- No CI maintenance.
- No support for users of any kind.

If the archive needs to come back to life, fork it. Don't expect the
original to wake up.
