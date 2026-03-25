# Monolith Eval Layer

**Purpose:** Prove the system works. These scripts answer the question every applied AI interviewer asks: *"How do you know your system works?"*

---

## Quick Start

```bash
# 1. Seed the database with labeled test data
python demo_seed.py

# 2. Run all three evaluators
python eval/detection_quality.py --db monolith.db
python eval/system_metrics.py    --db monolith.db
python eval/narration_eval.py    --db monolith.db --verbose
```

---

## Metrics Summary

> Update this table after each eval run. This is what you show in interviews.

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| AssemblyChecker Precision | — | ≥ 0.85 | ⬜ |
| AssemblyChecker Recall | — | ≥ 0.70 | ⬜ |
| ContinuityChecker Precision | — | ≥ 0.85 | ⬜ |
| ContinuityChecker Recall | — | ≥ 0.70 | ⬜ |
| EconomicChecker Precision | — | ≥ 0.85 | ⬜ |
| Detection P95 Latency | — | < 500ms | ⬜ |
| Anomaly Rate (24h) | — | < 50/hr | ⬜ |
| Cost Per Report | — | < $0.01 | ⬜ |
| Poll Interval Drift | — | < 10% | ⬜ |
| Narration Composite Score | — | ≥ 0.70 | ⬜ |
| Hallucination Rate | — | ≤ 10% | ⬜ |

---

## Scripts

### `detection_quality.py`
Measures precision, recall, and F1 per detection checker against labeled ground truth.

Ground truth is defined in `EVAL_GROUND_TRUTH` at the top of the file. Keep this in sync with `demo_seed.py`.

```bash
python eval/detection_quality.py --db monolith.db
python eval/detection_quality.py --db monolith.db --json      # CI-friendly
python eval/detection_quality.py --db monolith.db --fail-on-regression  # exits 1 on failure
```

**To update ground truth:** After running `demo_seed.py`, inspect the `anomalies` table and add confirmed true positives to `EVAL_GROUND_TRUTH` in the script.

---

### `system_metrics.py`
Operational health: latency, anomaly rate, cost, and poll drift.

```bash
python eval/system_metrics.py --db monolith.db
python eval/system_metrics.py --db monolith.db --hours 48    # wider window
python eval/system_metrics.py --db monolith.db --json
```

**One-time setup required:** Add a `detection_cycles` table to your DB and instrument your detection engine to write cycle timing. See the NOTE at the top of `system_metrics.py` for the exact schema and instrumentation pattern.

**Cost tracking:** Add `input_tokens` and `output_tokens` columns to `bug_reports` and log token counts from the Anthropic API response. The cost calculation uses `usage.input_tokens` and `usage.output_tokens` from the API response object.

---

### `narration_eval.py`
Scores the quality of LLM-generated plain English narration.

```bash
python eval/narration_eval.py --db monolith.db
python eval/narration_eval.py --db monolith.db --verbose              # shows flagged reports
python eval/narration_eval.py --db monolith.db --report-id MNL-xxx    # single report
python eval/narration_eval.py --db monolith.db --fail-on-regression
```

**Scoring dimensions:**
- **Factual grounding** — does narration reference IDs/values from evidence?
- **Severity alignment** — does language match CRITICAL/HIGH/MEDIUM/LOW?
- **Actionability** — does it tell someone what to do?
- **Hallucination flag** — did LLM invent IDs or numbers not in evidence?

The hallucination check is deterministic (no second LLM call). It extracts numeric tokens and tx hashes from narration and checks their presence in the evidence block.

---

## CI Integration

Add to your test pipeline:

```bash
# In your CI script (GitHub Actions, etc.)
python demo_seed.py
python eval/detection_quality.py --db monolith.db --fail-on-regression
python eval/narration_eval.py    --db monolith.db --fail-on-regression
```

This gates merges on eval regression. Green eval = deployable.

---

## Design Decisions

**Why deterministic scoring for narration, not LLM-as-judge?**  
LLM-grading-LLM adds cost, latency, and variance. The most important failure mode — hallucinated IDs and transaction hashes — is detectable with exact string matching. Deterministic checks are reproducible and auditable.

**Why macro-average for detection quality?**  
Each checker should independently meet the threshold. A system where CoordinatedBuying is 0.95 but SybilActivity is 0.40 is not a good system — the macro average would mask that. Each checker is evaluated independently.

**Why ground truth in-code rather than a fixture file?**  
Proximity to the eval logic makes drift visible. When `demo_seed.py` changes and tests break, the failure message points directly at the ground truth list.
