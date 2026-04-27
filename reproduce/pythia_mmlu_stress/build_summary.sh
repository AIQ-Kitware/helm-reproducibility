#!/usr/bin/env bash
# Build the aggregate publication surface for the Pythia × MMLU virtual
# experiment: story-arc sankeys, agreement curves, prioritized examples,
# README. Runs against the synthesized index slice produced by compose.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUDIT_STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
MANIFEST_FPATH="${MANIFEST_FPATH:-$ROOT/configs/virtual-experiments/pythia-mmlu-stress.yaml}"
PYTHON_BIN="${PYTHON_BIN:-python}"

cd "$ROOT"

# Pull the virtual experiment name + output root straight from the manifest
# so the script stays in sync if either is renamed in the YAML.
read -r EXPERIMENT_NAME OUTPUT_ROOT <<<"$("$PYTHON_BIN" -c "
import sys, yaml
data = yaml.safe_load(open('$MANIFEST_FPATH'))
print(data['name'], data['output']['root'])
")"

INDEX_FPATH="$OUTPUT_ROOT/indexes/audit_results_index.csv"
SUMMARY_ROOT="$OUTPUT_ROOT/reports/aggregate-summary"

if [[ ! -f "$INDEX_FPATH" ]]; then
    echo "synthesized index not found: $INDEX_FPATH" >&2
    echo "run ./compose.sh first." >&2
    exit 1
fi

PYTHONPATH="$ROOT" "$PYTHON_BIN" -m helm_audit.workflows.build_reports_summary \
    --experiment-name "$EXPERIMENT_NAME" \
    --index-fpath "$INDEX_FPATH" \
    --summary-root "$SUMMARY_ROOT" \
    "$@"

echo
echo "Aggregate publication surface: $SUMMARY_ROOT"
