#!/usr/bin/env bash
# Re-index the local audit results so the new pythia-12b-v0 run shows up
# in $AUDIT_STORE_ROOT/indexes/audit_results_index.latest.csv. Done on
# aiq-gpu before rsync so the index travels with the run data.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
EXP="${EXP_NAME:-audit-pythia-12b-mmlu-smoke}"

cd "$ROOT"

# Sanity: did anything actually land?
RESULTS_ROOT="${AUDIT_RESULTS_ROOT:-/data/crfm-helm-audit}"
EXP_DIR="$RESULTS_ROOT/$EXP"
if [[ ! -d "$EXP_DIR" ]]; then
  echo "FAIL: no run dir at $EXP_DIR; did 20_run.sh succeed?" >&2
  exit 1
fi
echo "found run dir: $EXP_DIR"
find "$EXP_DIR" -maxdepth 4 -name 'run_spec.json' | head -5

echo
echo "== eval-audit-index =="
eval-audit-index --output-dir "$STORE_ROOT/indexes"

echo
echo "OK: index refreshed. Latest CSV: $STORE_ROOT/indexes/audit_results_index.latest.csv"
echo "Now rsync /data/crfm-helm-audit/$EXP and /data/crfm-helm-audit-store/indexes back."
