#!/usr/bin/env bash
# Preflight for the pythia-12b-v0 × MMLU smoke run.
#
# Verifies:
#   - eval_audit CLI scripts are on $PATH
#   - a GPU is visible to nvidia-smi (and reports free VRAM)
#   - the audit data store dir exists / is writable
#   - HuggingFace cache dir is writable
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
RESULTS_ROOT="${AUDIT_RESULTS_ROOT:-/data/crfm-helm-audit}"
HF_CACHE_DIR="${HF_HOME:-$HOME/.cache/huggingface}"

cd "$ROOT"

echo "== eval_audit env =="
which eval-audit-check-env || { echo "FAIL: eval-audit-check-env not on PATH; run 'uv pip install -e .' first" >&2; exit 1; }
eval-audit-check-env

echo
echo "== GPU =="
if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "FAIL: nvidia-smi not found; this runbook requires a GPU on aiq-gpu" >&2
  exit 1
fi
nvidia-smi --query-gpu=name,memory.free,memory.total --format=csv
echo "(pythia-12b-v0 needs ~24 GB VRAM at fp16; verify a single GPU has enough free)"

echo
echo "== paths =="
mkdir -p "$STORE_ROOT/configs/manifests" "$RESULTS_ROOT" "$HF_CACHE_DIR"
echo "AUDIT_STORE_ROOT     = $STORE_ROOT"
echo "AUDIT_RESULTS_ROOT   = $RESULTS_ROOT"
echo "HF_HOME              = $HF_CACHE_DIR"
df -h "$RESULTS_ROOT" "$HF_CACHE_DIR" | sed 's/^/    /'

echo
echo "== helm-run =="
if command -v helm-run >/dev/null 2>&1; then
  echo "helm-run found at: $(command -v helm-run)"
  python -c "import helm; print('helm package:', helm.__file__)" || true
else
  echo "WARN: helm-run not on PATH; eval-audit-run will fail. uv pip install 'crfm-helm[all]'."
fi

echo
echo "OK: preflight passed."
