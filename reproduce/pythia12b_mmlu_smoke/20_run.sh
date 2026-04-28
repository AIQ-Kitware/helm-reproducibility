#!/usr/bin/env bash
# Execute the pythia-12b-v0 × MMLU smoke run via the dormant
# eval-audit-run / kwdagger / magnet / helm-run chain.
#
# This is the long-running step. Expect minutes-to-hours depending on the GPU.
# Output lands at $AUDIT_RESULTS_ROOT/<EXP>/helm/helm_id_*/...
#
# If this fails (the dormant kwdagger path may have bit-rotted), see the
# Fallback section in this directory's README for a direct helm-run command.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
EXP="${EXP_NAME:-audit-pythia-12b-mmlu-smoke}"

cd "$ROOT"

MANIFEST_FPATH="$STORE_ROOT/configs/manifests/$EXP.yaml"
if [[ ! -f "$MANIFEST_FPATH" ]]; then
  echo "FAIL: manifest not found at $MANIFEST_FPATH; run 10_make_manifest.sh first" >&2
  exit 1
fi

# Step 1 — preview the kwdagger argv this manifest would generate. Useful as
# a fast failure check before kicking off the long run.
echo "== preview (eval-audit-run --run=0) =="
eval-audit-run --run=0 "$MANIFEST_FPATH"

# Step 2 — the real execution. --run=1 is the only thing that does any work.
echo
echo "== execute (eval-audit-run --run=1) =="
eval-audit-run --run=1 "$MANIFEST_FPATH"

echo
echo "OK: run finished. Inspect output under \$AUDIT_RESULTS_ROOT/$EXP/helm/."
