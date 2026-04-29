#!/usr/bin/env bash
# Execute the pythia-12b-v0 grid run via the dormant
# eval-audit-run / kwdagger / magnet / helm-run chain.
#
# This is the long-running step. Expect minutes-to-hours depending on
# the GPU. Output lands at $AUDIT_RESULTS_ROOT/<EXP>/helm/helm_id_*/...
#
# HELM's compute_if_missing mode skips run-specs that already produced a
# DONE marker, so re-invoking after a partial run picks up where the
# previous attempt left off. The preflight below lists the run-specs that
# are already DONE on this machine so the user can see what will be
# skipped vs. what's about to run.
#
# If this fails (the dormant kwdagger path may have bit-rotted), see the
# Fallback section in this directory's README for a direct helm-run command.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
RESULTS_ROOT="${AUDIT_RESULTS_ROOT:-/data/crfm-helm-audit}"
EXP="${EXP_NAME:-audit-pythia-12b-mmlu-smoke}"

cd "$ROOT"

MANIFEST_FPATH="$STORE_ROOT/configs/manifests/$EXP.yaml"
if [[ ! -f "$MANIFEST_FPATH" ]]; then
  echo "FAIL: manifest not found at $MANIFEST_FPATH; run 10_make_manifest.sh first" >&2
  exit 1
fi

# == Preflight: which run-specs in this manifest already have a DONE run-dir ==
echo "== existing on-disk runs under $RESULTS_ROOT/$EXP =="
EXP_DIR="$RESULTS_ROOT/$EXP"
if [[ -d "$EXP_DIR" ]]; then
  # List manifest run_entries (with /-form, the key HELM resolves on),
  # then check for a corresponding DONE marker.
  MANIFEST_ENTRIES=$(awk '
    /^run_entries:/ {in_block=1; next}
    in_block && /^  - / {sub(/^  - /,""); print; next}
    in_block && /^[A-Za-z]/ {in_block=0}
  ' "$MANIFEST_FPATH")
  while IFS= read -r entry; do
    [[ -z "$entry" ]] && continue
    # HELM rewrites the run dir to use _-form for the model
    # (eleutherai/pythia-... -> eleutherai_pythia-...). Mirror that.
    name_us=$(printf '%s' "$entry" | sed 's|model=eleutherai/|model=eleutherai_|')
    matched=$(find "$EXP_DIR" -mindepth 4 -maxdepth 5 -type f -name DONE 2>/dev/null \
              | xargs -I{} dirname {} 2>/dev/null \
              | grep -F "/${name_us}" | head -1 || true)
    if [[ -n "$matched" ]]; then
      echo "  DONE     $entry"
    else
      echo "  pending  $entry"
    fi
  done <<<"$MANIFEST_ENTRIES"
else
  echo "  (no prior runs at $EXP_DIR; HELM will run every entry from scratch)"
fi
echo

# Step 1 — preview the kwdagger argv this manifest would generate.
echo "== preview (eval-audit-run --run=0) =="
eval-audit-run --run=0 "$MANIFEST_FPATH"

# Step 2 — the real execution. --run=1 is the only thing that does any work.
echo
echo "== execute (eval-audit-run --run=1) =="
eval-audit-run --run=1 "$MANIFEST_FPATH"

echo
echo "OK: run finished. Inspect output under $EXP_DIR/helm/."
