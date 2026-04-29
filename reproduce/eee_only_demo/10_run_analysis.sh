#!/usr/bin/env bash
# Run the EEE-only analysis on the demo fixture.
#
# Inputs:
#   tests/fixtures/eee_only_demo/eee_artifacts/   (checked-in fixture)
#
# Outputs:
#   ${OUT_DPATH:-/tmp/eee_only_demo_out}/
#     official_public_index.latest.csv
#     audit_results_index.latest.csv
#     planning/
#     core-reports/<packet>/core_metric_report.latest.{txt,json,png}
#
# Override OUT_DPATH to write somewhere else.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

OUT_DPATH="${OUT_DPATH:-/tmp/eee_only_demo_out}"
EEE_ROOT="${EEE_ROOT:-tests/fixtures/eee_only_demo/eee_artifacts}"

if [ ! -d "$EEE_ROOT" ]; then
  echo "FAIL: fixture root '$EEE_ROOT' does not exist." >&2
  echo "      Run ./reproduce/eee_only_demo/00_build_fixture.sh first." >&2
  exit 1
fi

eval-audit-from-eee \
  --eee-root "$EEE_ROOT" \
  --out-dpath "$OUT_DPATH" \
  --clean

echo
echo "Per-packet reports:"
ls -1 "$OUT_DPATH/core-reports/" | sed 's|^|  |'
echo
echo "Quick read: $OUT_DPATH/core-reports/<packet>/core_metric_report.latest.txt"
