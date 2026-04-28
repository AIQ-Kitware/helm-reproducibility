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

# --analysis-root points the per-packet scan at the virtual experiment's
# own analysis tree. Without it, _load_all_repro_rows scans only the
# canonical/publication/legacy locations and finds zero rows here, so
# prioritized examples and breakdowns come up empty.
#
# --no-filter-inventory suppresses the Stage-1 filter funnel artifacts
# (filter_selection_by_model, sankey_s02_filter_to_attempt,
# sankey_s04_end_to_end, and the discovered/selected cardinality lines).
# A virtual experiment is *already* a pre-filtered slice; the global
# discover->select funnel doesn't describe its denominator and the
# excluded-by-stage-1 visualization is misleading in this scope.
PYTHONPATH="$ROOT" "$PYTHON_BIN" -m helm_audit.workflows.build_reports_summary \
    --experiment-name "$EXPERIMENT_NAME" \
    --index-fpath "$INDEX_FPATH" \
    --summary-root "$SUMMARY_ROOT" \
    --analysis-root "$OUTPUT_ROOT" \
    --no-filter-inventory \
    "$@"

echo
echo "Aggregate publication surface: $SUMMARY_ROOT"
