#!/usr/bin/env bash
# Execute the smoke manifest: 2 run-entries, max_eval_instances=5 each.
#
# Lands at $AUDIT_RESULTS_ROOT/audit-finish-qwen25-gptoss-smoke/. Each
# run-spec gets its own subdir; ``mode: compute_if_missing`` skips
# anything with a DONE marker so re-running is cheap.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
BUNDLE_ROOT="${BUNDLE_ROOT:-$STORE_ROOT/local-bundles/finish_qwen25_gptoss}"

cd "$ROOT"

if [[ ! -f "$BUNDLE_ROOT/smoke_manifest.yaml" ]]; then
  bash reproduce/finish_qwen25_gptoss/05_write_bundle.sh >/dev/null
fi

eval-audit-run --run=1 "$BUNDLE_ROOT/smoke_manifest.yaml"
echo
echo "Smoke run done. Inspect output under:"
echo "  ${AUDIT_RESULTS_ROOT:-/data/crfm-helm-audit}/audit-finish-qwen25-gptoss-smoke/"
