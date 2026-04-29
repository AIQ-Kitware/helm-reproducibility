#!/usr/bin/env bash
# Build a from_eee-shaped symlink tree from the existing pythia EEE
# artifacts on disk. No bytes copied; everything is a symlink.
#
# Output layout (the shape ``eval-audit-from-eee`` expects):
#
#   $OUT_TREE/
#     official/
#       mmlu/eleutherai/pythia-6.9b/<uuid>.{json,_samples.jsonl}
#       boolq/eleutherai/pythia-6.9b/<uuid>.{json,_samples.jsonl}
#     local/
#       audit-mmlu-usfp-pythia-r1/mmlu/eleutherai/pythia-6.9b/<uuid>.{json,_samples.jsonl}
#       audit-mmlu-usfp-pythia-r2/mmlu/eleutherai/pythia-6.9b/<uuid>.{json,_samples.jsonl}
#       audit-boolq-pythia-r1/boolq/eleutherai/pythia-6.9b/<uuid>.{json,_samples.jsonl}
#       audit-boolq-pythia-r2/boolq/eleutherai/pythia-6.9b/<uuid>.{json,_samples.jsonl}
#
# - Per official-side run, only **one** artifact is linked even when the
#   eee_output dir contains multiple (those are usually re-conversions of
#   the same upstream HELM run, not real repeats; the planner's
#   ``_latest_official_selection`` would just keep one anyway).
# - The local subdirs encode the audit-experiment name as the level
#   immediately under ``local/`` so ``from_eee._extract_artifact_meta``
#   picks them up as separate experiments — and so the planner emits a
#   ``local_repeat`` comparison between r1 and r2 for each benchmark.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
OUT_ROOT="${OUT_ROOT:-$STORE_ROOT/eee-only-smoke}"
OUT_TREE="$OUT_ROOT/eee_artifacts"

cd "$ROOT"

OFFICIAL_PUBLIC_ROOT="$STORE_ROOT/crfm-helm-public-eee-test/classic/v0.3.0"
LOCAL_ROOT="$STORE_ROOT/eee/local"

OFFICIAL_RUN_DIRS=(
  "$OFFICIAL_PUBLIC_ROOT/mmlu:subject=us_foreign_policy,method=multiple_choice_joint,model=eleutherai_pythia-6.9b,data_augmentation=canonical"
  "$OFFICIAL_PUBLIC_ROOT/boolq:model=eleutherai_pythia-6.9b,data_augmentation=canonical"
)

declare -A LOCAL_BENCHMARK
LOCAL_BENCHMARK[audit-mmlu-usfp-pythia-r1]=mmlu
LOCAL_BENCHMARK[audit-mmlu-usfp-pythia-r2]=mmlu
LOCAL_BENCHMARK[audit-boolq-pythia-r1]=boolq
LOCAL_BENCHMARK[audit-boolq-pythia-r2]=boolq

echo "Cleaning $OUT_TREE ..."
rm -rf "$OUT_TREE"
mkdir -p "$OUT_TREE/official" "$OUT_TREE/local"

# --- Official side: pick one artifact per run and symlink it under the
#     <benchmark>/<dev>/<model>/ tree.
echo
echo "== linking official artifacts =="
for run_dir in "${OFFICIAL_RUN_DIRS[@]}"; do
  src_aggregate="$(find "$run_dir/eee_output" -type f -name '*.json' ! -name '*_samples.jsonl' 2>/dev/null | sort | head -1)"
  if [ -z "$src_aggregate" ]; then
    echo "  FAIL: no aggregate JSON under $run_dir/eee_output" >&2
    exit 1
  fi
  src_dir="$(dirname "$src_aggregate")"        # .../mmlu/eleutherai/pythia-6.9b
  rel_under_eee_output="${src_dir#"$run_dir/eee_output/"}"  # mmlu/eleutherai/pythia-6.9b
  uuid="$(basename "$src_aggregate" .json)"
  src_samples="$src_dir/${uuid}_samples.jsonl"
  if [ ! -f "$src_samples" ]; then
    echo "  FAIL: missing samples sibling for $src_aggregate" >&2
    exit 1
  fi
  dst_dir="$OUT_TREE/official/$rel_under_eee_output"
  mkdir -p "$dst_dir"
  ln -sf "$src_aggregate" "$dst_dir/$uuid.json"
  ln -sf "$src_samples" "$dst_dir/${uuid}_samples.jsonl"
  echo "  linked: official/$rel_under_eee_output/$uuid.{json,_samples.jsonl}"
done

# --- Local side: each audit-experiment gets its own subdir so it lands as
#     a distinct experiment after compose; r1 and r2 sit side by side and
#     the planner emits local_repeat between them.
echo
echo "== linking local artifacts =="
for exp in "${!LOCAL_BENCHMARK[@]}"; do
  benchmark="${LOCAL_BENCHMARK[$exp]}"
  exp_root="$LOCAL_ROOT/$exp"
  src_aggregate="$(find "$exp_root" -path '*/eee_output/*' -name '*.json' ! -name '*_samples.jsonl' 2>/dev/null | sort | head -1)"
  if [ -z "$src_aggregate" ]; then
    echo "  FAIL: no aggregate JSON under $exp_root/.../eee_output/" >&2
    exit 1
  fi
  src_dir="$(dirname "$src_aggregate")"        # .../<benchmark>/<dev>/<model>
  uuid="$(basename "$src_aggregate" .json)"
  src_samples="$src_dir/${uuid}_samples.jsonl"
  if [ ! -f "$src_samples" ]; then
    echo "  FAIL: missing samples sibling for $src_aggregate" >&2
    exit 1
  fi
  # Path layout: local/<exp>/<benchmark>/<dev>/<model>/<uuid>...
  rel="$(realpath --relative-to="$exp_root" "$src_dir")"
  rel_after_eee="${rel#*eee_output/}"          # <benchmark>/<dev>/<model>
  dst_dir="$OUT_TREE/local/$exp/$rel_after_eee"
  mkdir -p "$dst_dir"
  ln -sf "$src_aggregate" "$dst_dir/$uuid.json"
  ln -sf "$src_samples" "$dst_dir/${uuid}_samples.jsonl"
  echo "  linked: local/$exp/$rel_after_eee/$uuid.{json,_samples.jsonl}"
done

echo
echo "Tree ready at: $OUT_TREE"
echo "Next: ./20_run.sh   (or set OUT_ROOT/OUT_TREE to override)"
