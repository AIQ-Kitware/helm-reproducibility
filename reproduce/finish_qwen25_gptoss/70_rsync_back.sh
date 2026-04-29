#!/usr/bin/env bash
# Push the finish-qwen25-gptoss run dirs and the refreshed audit
# index back to the analysis host so the EEE Case Study 3 numbers can
# be regenerated against the new data.
#
# Required env:
#   RSYNC_DEST          rsync destination for the run dirs.
#                       Example: jon@analysis-host:/data/crfm-helm-audit/
#   RSYNC_DEST_INDEXES  rsync destination for the indexes dir.
#                       Example: jon@analysis-host:/data/crfm-helm-audit-store/indexes/
#
# Optional env:
#   AUDIT_RESULTS_ROOT  source results root (default /data/crfm-helm-audit)
#   AUDIT_STORE_ROOT    source store root (default /data/crfm-helm-audit-store)
#   RSYNC_FLAGS         override the default rsync flags
#                       (default: -aP --info=progress2)
#
# After this lands on the analysis host, regenerate the audit numbers
# with:
#   ./reproduce/open_helm_models_reproducibility/compose.sh
#   ./reproduce/open_helm_models_reproducibility/build_summary.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESULTS_ROOT="${AUDIT_RESULTS_ROOT:-/data/crfm-helm-audit}"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
RSYNC_FLAGS="${RSYNC_FLAGS:--aP --info=progress2}"

if [[ -z "${RSYNC_DEST:-}" ]]; then
  echo "FAIL: RSYNC_DEST is not set" >&2
  echo "  e.g. RSYNC_DEST=jon@analysis-host:/data/crfm-helm-audit/" >&2
  exit 1
fi
if [[ -z "${RSYNC_DEST_INDEXES:-}" ]]; then
  echo "FAIL: RSYNC_DEST_INDEXES is not set" >&2
  echo "  e.g. RSYNC_DEST_INDEXES=jon@analysis-host:/data/crfm-helm-audit-store/indexes/" >&2
  exit 1
fi

cd "$ROOT"

EXPS=(
  audit-finish-qwen25-gptoss-smoke
  audit-finish-qwen25-gptoss
)

for exp in "${EXPS[@]}"; do
  src="$RESULTS_ROOT/$exp"
  if [[ ! -d "$src" ]]; then
    echo "skip: $src (no run dir; this experiment didn't run on this host)"
    continue
  fi
  echo "== rsyncing $exp =="
  # shellcheck disable=SC2086
  rsync $RSYNC_FLAGS "$src" "$RSYNC_DEST"
done

echo
echo "== rsyncing index =="
# shellcheck disable=SC2086
rsync $RSYNC_FLAGS \
  "$STORE_ROOT/indexes/audit_results_index.csv" \
  "$STORE_ROOT/indexes/audit_results_index.jsonl" \
  "$STORE_ROOT/indexes/audit_results_index.txt" \
  "$RSYNC_DEST_INDEXES"

echo
echo "DONE. On the analysis host, regenerate the Case Study 3 numbers:"
echo "  cd <eval_audit checkout>"
echo "  ./reproduce/open_helm_models_reproducibility/compose.sh"
echo "  ./reproduce/open_helm_models_reproducibility/build_summary.sh"
