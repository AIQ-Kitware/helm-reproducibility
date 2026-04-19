#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT"
bash reproduce/small_models_kubeai/00_check_env.sh
bash reproduce/small_models_kubeai/05_deploy_models.sh
bash reproduce/small_models_kubeai/15_wait_ready.sh
bash reproduce/small_models_kubeai/10_write_bundle.sh
bash reproduce/small_models_kubeai/30_run_smoke.sh
bash reproduce/small_models_kubeai/50_run_full.sh
