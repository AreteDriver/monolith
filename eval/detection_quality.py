"""
eval/detection_quality.py

Detection Quality Evaluator for Monolith.

Measures precision, recall, and F1 per checker against labeled ground truth.
Ground truth is defined in EVAL_GROUND_TRUTH below — update when demo_seed.py changes.

Usage:
    python eval/detection_quality.py
    python eval/detection_quality.py --db path/to/monolith.db
    python eval/detection_quality.py --json   # machine-readable output
"""

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Ground Truth Registry
# ---------------------------------------------------------------------------
# These are the anomaly_ids seeded by demo_seed.py that are KNOWN TRUE POSITIVES.
# Any anomaly in the DB that is NOT in this list and fires for the same
# object/type combination is a false positive.
#
# HOW TO MAINTAIN: After running demo_seed.py, audit the anomalies table and
# record confirmed true positives here. Format: (anomaly_type, object_id)
#
# NOTE: object_id values here must match what demo_seed.py inserts.
# ---------------------------------------------------------------------------
EVAL_GROUND_TRUTH: list[tuple[str, str]] = [
    # (anomaly_type, object_id)
    # Kept in sync with demo_seed.py DEMO_ANOMALIES.
    #
    # --- AssemblyChecker ---
    ("PHANTOM_ITEM_CHANGE", "0x4f2a8c91d3e7b5f2a8c91d3e7b5f2a8c91d3e7b5"),
    ("UNEXPLAINED_OWNERSHIP_CHANGE", "0xc5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3"),
    # --- ContinuityChecker ---
    ("RESURRECTION", "0xa7b3c1d9e8f2a4b6c8d0e2f4a6b8c0d2e4f6a8b0"),
    ("STATE_GAP", "0xa7b3c1d9e8f2a4b6c8d0e2f4a6b8c0d2e4f6a8b0"),
    ("ORPHAN_OBJECT", "0xff00ee11dd22cc33bb44aa5599886677ff00ee11"),
    # --- EconomicChecker ---
    ("SUPPLY_DISCREPANCY", "0x4f2a8c91d3e7b5f2a8c91d3e7b5f2a8c91d3e7b5"),
]

# Anomaly types that belong to each checker (for grouping results).
# Must cover every type present in EVAL_GROUND_TRUTH above.
CHECKER_TYPES: dict[str, list[str]] = {
    "AssemblyChecker": ["PHANTOM_ITEM_CHANGE", "UNEXPLAINED_OWNERSHIP_CHANGE"],
    "ContinuityChecker": ["RESURRECTION", "STATE_GAP", "ORPHAN_OBJECT"],
    "EconomicChecker": ["SUPPLY_DISCREPANCY"],
}


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------
# ANSI color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


@dataclass
class CheckerResult:
    checker_name: str
    anomaly_types: list[str]
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    notes: str = ""

    def passed(self) -> bool:
        """True if precision >= 0.85 and recall >= 0.70 (minimum bar)."""
        return self.precision >= 0.85 and self.recall >= 0.70


@dataclass
class EvalSummary:
    db_path: str
    total_anomalies_in_db: int
    checkers: list[CheckerResult]
    overall_precision: float
    overall_recall: float
    overall_f1: float
    passed: bool


# ---------------------------------------------------------------------------
# Core Logic
# ---------------------------------------------------------------------------
def load_detected_anomalies(db_path: str) -> list[tuple[str, str]]:
    """
    Returns list of (anomaly_type, object_id) for all anomalies in the DB
    that are not marked FALSE_POSITIVE.
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT anomaly_type, object_id
            FROM anomalies
            WHERE status != 'FALSE_POSITIVE'
            """
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]
    finally:
        conn.close()


def count_total_anomalies(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM anomalies")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def compute_checker_result(
    checker_name: str,
    anomaly_types: list[str],
    detected: list[tuple[str, str]],
    ground_truth: list[tuple[str, str]],
) -> CheckerResult:
    """
    Compute precision/recall/F1 for a single checker.

    - true_positive:  in ground_truth AND in detected
    - false_positive: in detected BUT NOT in ground_truth
    - false_negative: in ground_truth BUT NOT in detected
    """
    # Filter to this checker's types
    gt_set = {(t, o) for t, o in ground_truth if t in anomaly_types}
    detected_set = {(t, o) for t, o in detected if t in anomaly_types}

    tp = len(gt_set & detected_set)
    fp = len(detected_set - gt_set)
    fn = len(gt_set - detected_set)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    notes = ""
    if tp + fp + fn == 0:
        notes = "No ground truth or detections for this checker — update EVAL_GROUND_TRUTH"

    return CheckerResult(
        checker_name=checker_name,
        anomaly_types=anomaly_types,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        notes=notes,
    )


def run_eval(db_path: str) -> EvalSummary:
    detected = load_detected_anomalies(db_path)
    total = count_total_anomalies(db_path)

    checkers: list[CheckerResult] = []
    for checker_name, anomaly_types in CHECKER_TYPES.items():
        result = compute_checker_result(checker_name, anomaly_types, detected, EVAL_GROUND_TRUTH)
        checkers.append(result)

    # Aggregate across all checkers (macro average)
    if checkers:
        overall_precision = sum(c.precision for c in checkers) / len(checkers)
        overall_recall = sum(c.recall for c in checkers) / len(checkers)
        overall_f1 = sum(c.f1 for c in checkers) / len(checkers)
    else:
        overall_precision = overall_recall = overall_f1 = 0.0

    passed = all(c.passed() for c in checkers)

    return EvalSummary(
        db_path=db_path,
        total_anomalies_in_db=total,
        checkers=checkers,
        overall_precision=round(overall_precision, 4),
        overall_recall=round(overall_recall, 4),
        overall_f1=round(overall_f1, 4),
        passed=passed,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def print_table(summary: EvalSummary) -> None:
    def color(val: float, threshold: float) -> str:
        c = GREEN if val >= threshold else RED
        return f"{c}{val:.4f}{RESET}"

    print(f"\n{'=' * 65}")
    print("  MONOLITH DETECTION QUALITY EVAL")
    print(f"  DB: {summary.db_path}  |  Total anomalies: {summary.total_anomalies_in_db}")
    print(f"{'=' * 65}")
    print(f"  {'Checker':<30} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Pass':>6}")
    print(f"  {'-' * 57}")

    for c in summary.checkers:
        status = f"{GREEN}✓{RESET}" if c.passed() else f"{RED}✗{RESET}"
        print(
            f"  {c.checker_name:<30} "
            f"{color(c.precision, 0.85):>10} "
            f"{color(c.recall, 0.70):>10} "
            f"{color(c.f1, 0.77):>10} "
            f"{status:>6}"
        )
        if c.notes:
            print(f"  {'':30} {YELLOW}⚠ {c.notes}{RESET}")

    print(f"  {'-' * 57}")
    overall_status = f"{GREEN}PASS{RESET}" if summary.passed else f"{RED}FAIL{RESET}"
    print(
        f"  {'OVERALL (macro avg)':<30} "
        f"{color(summary.overall_precision, 0.85):>10} "
        f"{color(summary.overall_recall, 0.70):>10} "
        f"{color(summary.overall_f1, 0.77):>10} "
        f"{overall_status:>6}"
    )
    print(f"{'=' * 65}")
    print("  Targets: Precision >= 0.85  |  Recall >= 0.70\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Monolith Detection Quality Evaluator")
    parser.add_argument(
        "--db",
        default="monolith.db",
        help="Path to SQLite database (default: monolith.db)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of table",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit code 1 if any checker fails threshold (use in CI)",
    )
    args = parser.parse_args()

    try:
        summary = run_eval(args.db)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print(
            "Run demo_seed.py first to populate the database, then re-run eval.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.json:
        # Convert dataclasses to dict, handle nested list
        out = asdict(summary)
        print(json.dumps(out, indent=2))
    else:
        print_table(summary)

    if args.fail_on_regression and not summary.passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
