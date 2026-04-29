#!/usr/bin/env bash
# Dry-run the full manifest: ~24 run-entries spanning Qwen 2.5 +
# gpt-oss missing benchmarks. Use this to confirm every entry resolves
# before kicking off the long run. Entries that don't resolve here will
# fail visibly (typically because the local crfm-helm install doesn't
# yet support a v1.12.0 / v1.14.0 scenario — see README "Caveats").
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
BUNDLE_ROOT="${BUNDLE_ROOT:-$STORE_ROOT/local-bundles/finish_qwen25_gptoss}"

cd "$ROOT"

if [[ ! -f "$BUNDLE_ROOT/full_manifest.yaml" ]]; then
  bash reproduce/finish_qwen25_gptoss/05_write_bundle.sh >/dev/null
fi

eval-audit-run --run=0 "$BUNDLE_ROOT/full_manifest.yaml"
