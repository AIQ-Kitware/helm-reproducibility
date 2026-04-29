#!/usr/bin/env bash
# Write the eval-audit benchmark bundle for the finish_qwen25_gptoss
# preset. The bundle materializes the smoke + full HELM manifests and
# the run_details.yaml that pins the LiteLLM router URL + per-model
# deployment names.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
BUNDLE_ROOT="${BUNDLE_ROOT:-$STORE_ROOT/local-bundles/finish_qwen25_gptoss}"
ENV_FPATH="${LITELLM_ENV_FPATH:-/data/service/service-repo/vllm/generated/.env}"
LITELLM_BASE_URL="${LITELLM_BASE_URL:-http://localhost:14000}"

if [[ -f "$ENV_FPATH" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FPATH"
fi

cd "$ROOT"
python -m eval_audit.integrations.vllm_service export-benchmark-bundle \
  --preset finish_qwen25_gptoss \
  --bundle-root "$BUNDLE_ROOT" \
  --base-url "${LITELLM_BASE_URL}/v1"

echo
echo "Bundle: $BUNDLE_ROOT"
echo "  smoke manifest: $BUNDLE_ROOT/smoke_manifest.yaml"
echo "  full manifest:  $BUNDLE_ROOT/manifest.yaml"
