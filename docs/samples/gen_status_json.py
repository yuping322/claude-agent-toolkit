#!/usr/bin/env python3
"""Generate a status.json artifact (sample)."""
from __future__ import annotations
import json, time, os, sys

task_id = os.environ.get("TASK_ID", "add-payment-tests")
branch = os.environ.get("BRANCH", f"auto/{task_id}")
status = {
    "id": task_id,
    "branch": branch,
    "commits": int(os.environ.get("COMMITS", "1")),
    "tests_passed": int(os.environ.get("TESTS_PASSED", "120")),
    "tests_failed": int(os.environ.get("TESTS_FAILED", "0")),
    "coverage_before": float(os.environ.get("COV_BEFORE", "72.1")),
    "coverage_after": float(os.environ.get("COV_AFTER", "74.3")),
    "lint_errors": int(os.environ.get("LINT_ERRORS", "0")),
    "type_errors": int(os.environ.get("TYPE_ERRORS", "0")),
    "risk_labels": os.environ.get("RISK_LABELS", "").split() if os.environ.get("RISK_LABELS") else [],
    "partial": os.environ.get("PARTIAL", "false") == "true",
    "pr_url": os.environ.get("PR_URL", ""),
    "finished_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
}
out = sys.argv[1] if len(sys.argv) > 1 else f"status.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(status, f, ensure_ascii=False, indent=2)
print(f"[INFO] Wrote {out}")
