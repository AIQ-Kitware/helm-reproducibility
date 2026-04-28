#!/usr/bin/env bash
# Generate the manifest YAML for the pythia-12b-v0 × MMLU smoke run.
#
# The eval-audit-make-manifest helper reads from $STORE_ROOT/configs/run_specs.yaml,
# but pythia-12b-v0 was filtered out of that selection (size gate) so the helper
# can't produce this manifest. We write the manifest directly. The format matches
# eval_audit/manifests/models.py:ManifestSpec.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
EXP="${EXP_NAME:-audit-pythia-12b-mmlu-smoke}"
SUBJECT="${HELM_MMLU_SUBJECT:-abstract_algebra}"
MAX_EVAL_INSTANCES="${MAX_EVAL_INSTANCES:-1000}"
DEVICES="${DEVICES:-0}"
TMUX_WORKERS="${TMUX_WORKERS:-1}"

MANIFEST_FPATH="$STORE_ROOT/configs/manifests/$EXP.yaml"
mkdir -p "$(dirname "$MANIFEST_FPATH")"

cat >"$MANIFEST_FPATH" <<EOF
schema_version: 1
experiment_name: $EXP
description: >-
  Smoke run of eleutherai/pythia-12b-v0 on MMLU subject=$SUBJECT, exercising
  the eval-audit-run / kwdagger / magnet / helm-run execution path. One run
  entry; HELM dynamically registers the huggingface deployment via
  --enable-huggingface-models.
run_entries:
  - mmlu:subject=$SUBJECT,method=multiple_choice_joint,model=eleutherai/pythia-12b-v0,data_augmentation=canonical
suite: $EXP
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
enable_huggingface_models:
  - eleutherai/pythia-12b-v0
enable_local_huggingface_models: []
EOF

echo "wrote: $MANIFEST_FPATH"
echo
cat "$MANIFEST_FPATH"
