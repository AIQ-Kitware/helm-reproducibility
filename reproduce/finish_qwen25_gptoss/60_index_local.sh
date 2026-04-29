#!/usr/bin/env bash
# Re-index the local audit results so the new finish-qwen25-gptoss runs
# show up in $AUDIT_STORE_ROOT/indexes/audit_results_index.csv.
# Done before rsync so the index travels with the run data.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
RESULTS_ROOT="${AUDIT_RESULTS_ROOT:-/data/crfm-helm-audit}"

cd "$ROOT"

# Sanity: did anything actually land?
for exp in audit-finish-qwen25-gptoss-smoke audit-finish-qwen25-gptoss; do
  exp_dir="$RESULTS_ROOT/$exp"
  if [[ ! -d "$exp_dir" ]]; then
    echo "skip: no run dir at $exp_dir (didn't run, or named differently)"
    continue
  fi
  echo "found: $exp_dir"
  find "$exp_dir" -maxdepth 4 -name 'run_spec.json' | head -3
done

echo
echo "== eval-audit-index =="
eval-audit-index \
  --results-root "$RESULTS_ROOT" \
  --report-dpath "$STORE_ROOT/indexes"

echo
echo "OK: index refreshed."
echo "Latest CSV: $STORE_ROOT/indexes/audit_results_index.csv"
echo "Next: ./70_rsync_back.sh"
