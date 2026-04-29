#!/usr/bin/env bash
# Verify that the EEE artifacts this runbook expects are present on disk.
#
# Inputs (all under $AUDIT_STORE_ROOT — default /data/crfm-helm-audit-store):
#
#   official/
#     classic/v0.3.0/mmlu:subject=us_foreign_policy,...,model=eleutherai_pythia-6.9b,...
#     classic/v0.3.0/boolq:model=eleutherai_pythia-6.9b,...
#
#   local/
#     audit-mmlu-usfp-pythia-r1/   audit-mmlu-usfp-pythia-r2/
#     audit-boolq-pythia-r1/       audit-boolq-pythia-r2/
#
# Each producing one (or more) <uuid>.json + <uuid>_samples.jsonl pair under
# its eee_output/<benchmark>/<dev>/<model>/ subdir.
#
# This step performs no writes. If any expected artifact is missing, fix
# that before running 10_link_tree.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"

cd "$ROOT"

OFFICIAL_PUBLIC_ROOT="$STORE_ROOT/crfm-helm-public-eee-test/classic/v0.3.0"
LOCAL_ROOT="$STORE_ROOT/eee/local"

OFFICIAL_DIRS=(
  "$OFFICIAL_PUBLIC_ROOT/mmlu:subject=us_foreign_policy,method=multiple_choice_joint,model=eleutherai_pythia-6.9b,data_augmentation=canonical"
  "$OFFICIAL_PUBLIC_ROOT/boolq:model=eleutherai_pythia-6.9b,data_augmentation=canonical"
)
LOCAL_EXPS=(
  audit-mmlu-usfp-pythia-r1
  audit-mmlu-usfp-pythia-r2
  audit-boolq-pythia-r1
  audit-boolq-pythia-r2
)

errors=0

echo "== official EEE artifacts =="
for dir in "${OFFICIAL_DIRS[@]}"; do
  count="$(find "$dir/eee_output" -type f -name '*.json' ! -name '*_samples.jsonl' 2>/dev/null | wc -l)"
  if [ "$count" -lt 1 ]; then
    echo "  FAIL: no artifacts under $dir/eee_output" >&2
    errors=$((errors+1))
  else
    echo "  OK ($count): ${dir##*/}"
  fi
done

echo
echo "== local EEE artifacts =="
for exp in "${LOCAL_EXPS[@]}"; do
  exp_root="$LOCAL_ROOT/$exp"
  if [ ! -d "$exp_root" ]; then
    echo "  FAIL: missing $exp_root" >&2
    errors=$((errors+1))
    continue
  fi
  count="$(find "$exp_root" -path '*/eee_output/*' -name '*.json' ! -name '*_samples.jsonl' 2>/dev/null | wc -l)"
  if [ "$count" -lt 1 ]; then
    echo "  FAIL: no eee_output artifacts under $exp_root" >&2
    errors=$((errors+1))
  else
    echo "  OK ($count): $exp"
  fi
done

echo
if [ "$errors" -gt 0 ]; then
  echo "FAIL: $errors check(s) failed; cannot continue." >&2
  exit 1
fi
echo "OK: all expected EEE artifacts present."
