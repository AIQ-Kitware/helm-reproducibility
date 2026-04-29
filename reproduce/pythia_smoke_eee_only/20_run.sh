#!/usr/bin/env bash
# Run the EEE-only analysis pipeline against the symlink tree built by
# 10_link_tree.sh. Pure analysis; no model loads, no HF/torch downloads.
#
# Outputs (all under $OUT_ROOT, default $AUDIT_STORE_ROOT/eee-only-smoke):
#   $OUT_ROOT/from_eee_out/
#     audit_results_index.latest.csv
#     official_public_index.latest.csv
#     planning/
#     <experiment>/core-reports/<packet>/core_metric_report.latest.{txt,json,png}
#     aggregate-summary/all-results/                # cross-packet roll-up
#       README.latest.txt
#       agreement_curve.latest.{html,jpg}
#       reproducibility_buckets.latest.{html,jpg}
#       sankey_*.html
#       prioritized_examples.latest/
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
OUT_ROOT="${OUT_ROOT:-$STORE_ROOT/eee-only-smoke}"
OUT_TREE="${OUT_TREE:-$OUT_ROOT/eee_artifacts}"
FROM_EEE_OUT="${FROM_EEE_OUT:-$OUT_ROOT/from_eee_out}"

cd "$ROOT"

if [ ! -d "$OUT_TREE" ]; then
  echo "FAIL: artifact tree '$OUT_TREE' missing; run ./10_link_tree.sh first." >&2
  exit 1
fi

eval-audit-from-eee \
  --eee-root "$OUT_TREE" \
  --out-dpath "$FROM_EEE_OUT" \
  --clean \
  --build-aggregate-summary

echo
echo "Per-packet reports:"
find "$FROM_EEE_OUT" -mindepth 3 -maxdepth 3 -type d -path '*/core-reports/*' -printf '  %p\n' | sort
echo
echo "Aggregate summary: $FROM_EEE_OUT/aggregate-summary/all-results/README.latest.txt"
