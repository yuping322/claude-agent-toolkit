#!/usr/bin/env bash
set -euo pipefail
BRANCH=${BRANCH:-"auto/add-payment-tests"}

echo "[INFO] Attempting rebase"
git fetch origin
git checkout "$BRANCH"
set +e
git rebase origin/main
REB_EXIT=$?
set -e
if [ "$REB_EXIT" -ne 0 ]; then
  echo "[WARN] Rebase failed; aborting and requiring manual resolution"
  git rebase --abort || true
  exit 2
fi

echo "[INFO] Rebase successful; pushing"
git push -f origin "$BRANCH"
