#!/usr/bin/env bash
# Generate the manifest YAML for the pythia-12b-v0 grid run.
#
# Originally a 1-subject smoke (mmlu:abstract_algebra) on 2026-04-28 to
# exercise the dormant eval-audit-run / kwdagger / magnet / helm-run chain.
# That run reproduced the public HELM result exactly, so the runbook expanded
# first to all 5 MMLU subjects and now to the broader pythia-12b-v0 grid
# below. HELM's compute_if_missing mode skips already-DONE runs, so each
# expansion picks up where the previous one left off.
#
# Coverage:
#   * MMLU × 5 subjects: abstract_algebra, college_chemistry,
#     computer_security, econometrics, us_foreign_policy
#   * BoolQ
#   * IMDB
#   * TruthfulQA (mc_single, multiple_choice_joint)
#
# Override paths:
#   * HELM_MMLU_SUBJECTS — space-separated MMLU subject names
#       (default = the 5 subjects above; pass empty string to skip MMLU)
#   * HELM_EXTRA_RUN_ENTRIES — newline- or `;`-separated extra run-entry
#       strings (default = boolq + imdb + truthful_qa pythia-12b-v0;
#       pass empty string to keep the run mmlu-only)
#   * HELM_RUN_ENTRIES — full override; if set, replaces both lists above
#       and is the only thing fed to HELM. One run-entry per line.
#
# eval-audit-make-manifest helper isn't usable here because pythia-12b-v0
# was Stage-1-filtered out of $STORE_ROOT/configs/run_specs.yaml (size gate),
# so we write the manifest directly. Format matches
# eval_audit/manifests/models.py:ManifestSpec.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
EXP="${EXP_NAME:-audit-pythia-12b-mmlu-smoke}"

DEFAULT_SUBJECTS="abstract_algebra college_chemistry computer_security econometrics us_foreign_policy"
SUBJECTS="${HELM_MMLU_SUBJECTS-$DEFAULT_SUBJECTS}"

DEFAULT_EXTRA_RUN_ENTRIES="\
boolq:model=eleutherai/pythia-12b-v0,data_augmentation=canonical
imdb:model=eleutherai/pythia-12b-v0,data_augmentation=canonical
truthful_qa:task=mc_single,method=multiple_choice_joint,model=eleutherai/pythia-12b-v0,data_augmentation=canonical"
EXTRA_RUN_ENTRIES="${HELM_EXTRA_RUN_ENTRIES-$DEFAULT_EXTRA_RUN_ENTRIES}"

MAX_EVAL_INSTANCES="${MAX_EVAL_INSTANCES:-1000}"
DEVICES="${DEVICES:-0,1,2,3}"
TMUX_WORKERS="${TMUX_WORKERS:-4}"

MANIFEST_FPATH="$STORE_ROOT/configs/manifests/$EXP.yaml"
mkdir -p "$(dirname "$MANIFEST_FPATH")"

# Build the final run_entries list. If HELM_RUN_ENTRIES is set, use it
# verbatim; otherwise derive from MMLU subjects + extras.
RUN_ENTRIES_BLOCK=""
if [[ -n "${HELM_RUN_ENTRIES:-}" ]]; then
  while IFS= read -r entry; do
    [[ -z "$entry" ]] && continue
    RUN_ENTRIES_BLOCK+="  - ${entry}"$'\n'
  done <<<"$HELM_RUN_ENTRIES"
else
  for s in $SUBJECTS; do
    RUN_ENTRIES_BLOCK+="  - mmlu:subject=${s},method=multiple_choice_joint,model=eleutherai/pythia-12b-v0,data_augmentation=canonical"$'\n'
  done
  while IFS= read -r entry; do
    # Allow `;`-separated extras as well as newline-separated.
    while IFS=';' read -r piece; do
      piece="${piece## }"; piece="${piece%% }"
      [[ -z "$piece" ]] && continue
      RUN_ENTRIES_BLOCK+="  - ${piece}"$'\n'
    done <<<"$entry"
  done <<<"$EXTRA_RUN_ENTRIES"
fi

if [[ -z "$RUN_ENTRIES_BLOCK" ]]; then
  echo "FAIL: no run_entries — HELM_MMLU_SUBJECTS, HELM_EXTRA_RUN_ENTRIES, and HELM_RUN_ENTRIES are all empty" >&2
  exit 1
fi

# A short human description listing the unique benchmarks present.
BENCHMARK_DESC=$(printf '%s' "$RUN_ENTRIES_BLOCK" | awk -F'[: ]' '/^  - / {print $4}' | sort -u | paste -sd', ' -)

cat >"$MANIFEST_FPATH" <<EOF
schema_version: 1
experiment_name: $EXP
description: >-
  eleutherai/pythia-12b-v0 grid on benchmarks ($BENCHMARK_DESC), via HELM's
  built-in huggingface/pythia-12b-v0 deployment (HuggingFaceClient,
  EleutherAI/gpt-neox-20b tokenizer, max_sequence_length 2048). Runs
  through eval-audit-run / kwdagger / magnet / helm-run on aiq-gpu.
run_entries:
${RUN_ENTRIES_BLOCK}suite: $EXP
max_eval_instances: $MAX_EVAL_INSTANCES
mode: compute_if_missing
materialize: symlink
backend: tmux
devices: "$DEVICES"
tmux_workers: $TMUX_WORKERS
local_path: prod_env
precomputed_root: null
require_per_instance_stats: true
model_deployments_fpath: null
enable_huggingface_models: []
enable_local_huggingface_models: []
EOF

echo "wrote: $MANIFEST_FPATH"
echo
cat "$MANIFEST_FPATH"
