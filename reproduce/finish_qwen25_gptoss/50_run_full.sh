#!/usr/bin/env bash
# Execute the full manifest. Long-running: ~24 HELM run-entries at
# max_eval_instances=1000 each (override with MAX_EVAL_INSTANCES=...).
#
# Output lands at $AUDIT_RESULTS_ROOT/audit-finish-qwen25-gptoss/. The
# manifest uses ``mode: compute_if_missing``, so re-invocation skips
# any run-spec with a DONE marker. Safe to interrupt and resume.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
BUNDLE_ROOT="${BUNDLE_ROOT:-$STORE_ROOT/local-bundles/finish_qwen25_gptoss}"

cd "$ROOT"

if [[ ! -f "$BUNDLE_ROOT/manifest.yaml" ]]; then
  bash reproduce/finish_qwen25_gptoss/05_write_bundle.sh >/dev/null
fi

# Optional override: tighter / looser instance budget per run-spec.
EXTRA_ARGS=()
if [[ -n "${MAX_EVAL_INSTANCES:-}" ]]; then
  EXTRA_ARGS+=(--override-max-eval-instances "$MAX_EVAL_INSTANCES")
fi

eval-audit-run --run=1 "${EXTRA_ARGS[@]}" "$BUNDLE_ROOT/manifest.yaml"

echo
echo "Full run done. Output:"
echo "  ${AUDIT_RESULTS_ROOT:-/data/crfm-helm-audit}/audit-finish-qwen25-gptoss/"
echo "Next: ./60_index_local.sh   (refresh the audit index before rsync)"
