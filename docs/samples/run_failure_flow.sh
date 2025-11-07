#!/usr/bin/env bash
set -euo pipefail
TASK_ID="add-payment-tests"
FAIL_BRANCH="auto/${TASK_ID}-fail"
REPO_URL=${REPO_URL:-"git@github.com:org/sample-service.git"}

rm -rf sample-service || true
git clone "$REPO_URL" sample-service
cd sample-service

git fetch origin
git checkout main
git pull --ff-only
git checkout -b "$FAIL_BRANCH"

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt >/dev/null

mkdir -p artifacts/${TASK_ID}-fail

# Inject a failing test deliberately
cat > tests/test_payment.py <<'EOF'
import pytest
from src.service.payment import calculate_fee

def test_negative_fee():
    # Expecting error or specific behavior; placeholder assertion will fail
    assert calculate_fee(-10) == 0
EOF

set +e
coverage run -m pytest -q > artifacts/${TASK_ID}-fail/trace.txt 2>&1
TEST_EXIT=$?
set -e

if [ "$TEST_EXIT" -eq 0 ]; then
  echo "[UNEXPECTED] Failure scenario did not fail";
fi

cat > artifacts/${TASK_ID}-fail/FAILURE.md <<'EOF'
# Task Failure Report
Task: add-payment-tests
Branch: auto/add-payment-tests-fail
Phase: VALIDATE_TESTS
Failure: TESTS_FAILED
Summary: 新增的负数场景测试未通过，可能暴露 fee 逻辑缺陷。请人工核实。\n保留失败测试以便后续修复。
Next Steps:
1. 修复 calculate_fee 负数处理逻辑。
2. 重新运行任务：auto/add-payment-tests-retry-1。
EOF

git add artifacts/${TASK_ID}-fail tests/test_payment.py || true
git commit -m "fail: add-payment-tests aborted (TESTS_FAILED)"

git push -u origin "$FAIL_BRANCH" || true

echo "[INFO] Draft PR creation command:"
echo "gh pr create --title 'fail: add-payment-tests (TESTS_FAILED)' --body-file artifacts/${TASK_ID}-fail/FAILURE.md --label automated --label failure --draft"
