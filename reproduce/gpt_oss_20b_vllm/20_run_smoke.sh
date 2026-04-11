#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
helm-audit-run --run=1 configs/gpt_oss_20b_vllm_smoke_manifest.yaml
