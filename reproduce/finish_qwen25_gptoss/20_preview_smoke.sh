#!/usr/bin/env bash
# Dry-run the smoke manifest: ``eval-audit-run --run=0`` enumerates the
# scheduled HELM run-specs without executing them. Used to verify the
# manifest resolves before kicking off the real run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
BUNDLE_ROOT="${BUNDLE_ROOT:-$STORE_ROOT/local-bundles/finish_qwen25_gptoss}"

cd "$ROOT"

if [[ ! -f "$BUNDLE_ROOT/smoke_manifest.yaml" ]]; then
  bash reproduce/finish_qwen25_gptoss/05_write_bundle.sh >/dev/null
fi

eval-audit-run --run=0 "$BUNDLE_ROOT/smoke_manifest.yaml"
