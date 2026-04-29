#!/bin/bash
__doc__='

This document goes over the steps to compute kwdagger style runs for qwen35 on
HELM benchmarks.

We started writing this in the helm-audit repo:
b9844e305d378fc42512ec5c7996056f006efb04

Im assuming that weve setup a VLLM server on the aiq-gpu machine that we can
use.
'


### We assume there is an environment file that contains the API key.

# Loads: LITELLM_MASTER_KEY
source /data/service/service-repo/vllm/generated/.env
export LITELLM_BASE_URL=http://localhost:14000

# Check the server is online
curl -sS \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  ${LITELLM_BASE_URL}/v1/models


MODEL_ID=$(curl -sS \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  ${LITELLM_BASE_URL}/v1/models | jq -r '.data[0].id')
echo "MODEL_ID = $MODEL_ID"


# API smoke test
curl -sS \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  "${LITELLM_BASE_URL}/v1/chat/completions" \
  -d "{
    \"model\": \"$MODEL_ID\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"Reply with exactly: ok\"}
    ],
    \"max_tokens\": 8,
    \"temperature\": 0.0
  }" | jq


curl -sS \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  "${LITELLM_BASE_URL}/v1/chat/completions" \
  -d "{
    \"model\": \"$MODEL_ID\",
    \"messages\": [
      {
        \"role\": \"user\",
        \"content\": \"The following are multiple choice questions (with answers) about anatomy.\n\nQuestion: What is the embryological origin of the hyoid bone?\nA. The first pharyngeal arch\nB. The first and second pharyngeal arches\nC. The second pharyngeal arch\nD. The second and third pharyngeal arches\nAnswer: D\n\nQuestion: Which of these branches of the trigeminal nerve contain somatic motor processes?\nA. The supraorbital nerve\nB. The infraorbital nerve\nC. The mental nerve\nD. None of the above\nAnswer: D\n\nQuestion: Which of the following is the body cavity that contains the pituitary gland?\nA. Abdominal\nB. Cranial\nC. Pleural\nD. Spinal\nAnswer: B\n\nQuestion: The pleura\nA. have no sensory innervation.\nB. are separated by a 2 mm space.\nC. extend into the neck.\nD. are composed of respiratory epithelium.\nAnswer: C\n\nQuestion: In Angle's Class II Div 2 occlusion there is\nA. excess overbite of the upper lateral incisors.\nB. negative overjet of the upper central incisors.\nC. excess overjet of the upper lateral incisors.\nD. excess overjet of the upper central incisors.\nAnswer: C\n\nQuestion: Which one of the following brain areas is supplied by branches of the subclavian arteries?\nA. The frontal lobe\nB. The parietal lobe\nC. The hypothalamus\nD. The cerebellum\nAnswer:\"
      }
    ],
    \"max_tokens\": 1,
    \"temperature\": 0.0,
    \"stop\": [\"\\n\"]
  }" | jq


curl -sS \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  "${LITELLM_BASE_URL}/v1/completions" \
  -d "{
    \"model\": \"$MODEL_ID\",
    \"prompt\": \"The following are multiple choice questions (with answers) about anatomy.\n\nQuestion: What is the embryological origin of the hyoid bone?\nA. The first pharyngeal arch\nB. The first and second pharyngeal arches\nC. The second pharyngeal arch\nD. The second and third pharyngeal arches\nAnswer: D\n\nQuestion: Which of these branches of the trigeminal nerve contain somatic motor processes?\nA. The supraorbital nerve\nB. The infraorbital nerve\nC. The mental nerve\nD. None of the above\nAnswer: D\n\nQuestion: Which of the following is the body cavity that contains the pituitary gland?\nA. Abdominal\nB. Cranial\nC. Pleural\nD. Spinal\nAnswer: B\n\nQuestion: The pleura\nA. have no sensory innervation.\nB. are separated by a 2 mm space.\nC. extend into the neck.\nD. are composed of respiratory epithelium.\nAnswer: C\n\nQuestion: In Angle's Class II Div 2 occlusion there is\nA. excess overbite of the upper lateral incisors.\nB. negative overjet of the upper central incisors.\nC. excess overjet of the upper lateral incisors.\nD. excess overjet of the upper central incisors.\nAnswer: C\n\nQuestion: Which one of the following brain areas is supplied by branches of the subclavian arteries?\nA. The frontal lobe\nB. The parietal lobe\nC. The hypothalamus\nD. The cerebellum\nAnswer:\",
    \"max_tokens\": 1,
    \"temperature\": 0.0,
    \"stop\": [\"\\n\"]
  }" | jq


  curl -sS \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  "${LITELLM_BASE_URL}/v1/chat/completions" \
  -d "{
    \"model\": \"$MODEL_ID\",
    \"messages\": [
      {
        \"role\": \"user\",
        \"content\": \"Answer the following multiple choice question with only one capital letter: A, B, C, or D.\n\nQuestion: Which one of the following brain areas is supplied by branches of the subclavian arteries?\nA. The frontal lobe\nB. The parietal lobe\nC. The hypothalamus\nD. The cerebellum\"
      }
    ],
    \"max_tokens\": 1,
    \"temperature\": 0.0,
    \"stop\": [\"\\n\"]
  }" | jq


### Set up a writable local bundle outside the repo

export REPO_ROOT="${REPO_ROOT:-$HOME/code/helm_audit}"
export AUDIT_STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
export QWEN35_BUNDLE_ROOT="$AUDIT_STORE_ROOT/local-bundles/qwen35_vllm"

cd "$REPO_ROOT"

mkdir -p "$QWEN35_BUNDLE_ROOT"

printf 'REPO_ROOT=%s\n' "$REPO_ROOT"
printf 'AUDIT_STORE_ROOT=%s\n' "$AUDIT_STORE_ROOT"
printf 'QWEN35_BUNDLE_ROOT=%s\n' "$QWEN35_BUNDLE_ROOT"


### Write model deployments.yaml

export AUDIT_STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
export QWEN35_BUNDLE_ROOT="$AUDIT_STORE_ROOT/local-bundles/qwen35_vllm"
mkdir -p "$QWEN35_BUNDLE_ROOT"


cat > "$QWEN35_BUNDLE_ROOT/model_deployments.yaml" <<YAML
model_deployments:
  - name: litellm/qwen3.5-9b-local
    model_name: qwen/qwen3.5-9b
    tokenizer_name: qwen/qwen3.5-9b
    max_sequence_length: 32768
    client_spec:
      class_name: "helm.clients.openai_client.OpenAILegacyCompletionsClient"
      args:
        base_url: "${LITELLM_BASE_URL}/v1"
        api_key: "${LITELLM_MASTER_KEY}"
        openai_model_name: "qwen3.5-9b"
YAML

echo "Wrote:"
echo "  $QWEN35_BUNDLE_ROOT/model_deployments.yaml"
echo
cat "$QWEN35_BUNDLE_ROOT/model_deployments.yaml"


### Run a materialize smoke test that stages model_deployments.yaml into prod_env

export AUDIT_STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
export QWEN35_BUNDLE_ROOT="$AUDIT_STORE_ROOT/local-bundles/qwen35_vllm"
export MATERIALIZE_OUT="$QWEN35_BUNDLE_ROOT/materialize_smoke"

rm -rf "$MATERIALIZE_OUT"
mkdir -p "$MATERIALIZE_OUT"

# Test on a small MMLU subset
python -m magnet.backends.helm.cli.materialize_helm_run \
  --run-entry "mmlu:subject=anatomy,method=multiple_choice_joint,model=qwen/qwen3.5-9b" \
  --suite "audit-qwen35-materialize-smoke" \
  --max-eval-instances 10000 \
  --out-dpath "$MATERIALIZE_OUT" \
  --mode force_recompute \
  --local-path prod_env \
  --model-deployments-fpath "$QWEN35_BUNDLE_ROOT/model_deployments.yaml"

# Read results

python - <<'PY'
import json
import os
import ubelt as ub
from pathlib import Path

materialize_out = Path(os.environ['MATERIALIZE_OUT'])
adapter_manifest_fpath = materialize_out / "adapter_manifest.json"
adapter_manifest = json.loads(adapter_manifest_fpath.read_text())
run_dpath = Path(adapter_manifest["computed"]["computed_run_dir"])
print(f"run_dpath={run_dpath}")

from magnet.backends.helm import helm_outputs
run = helm_outputs.HelmRun.coerce(run_dpath)

import rich
stats_df = run.dataframe.stats()
flags = stats_df['stats.name.name'].apply(lambda x: x in {"exact_match", "logprob", "num_completion_tokens"})
interesting_stats = stats_df[flags]
interesting_stats = interesting_stats.prefix_subframe('stats', drop_prefix=True)

stats = run.json.stats()
per_instance_stats = run.json.per_instance_stats()
scenario_state = run.json.scenario_state()

adapter_spec = scenario_state["adapter_spec"]
print(f"model={adapter_spec['model']}")
print(f"model_deployment={adapter_spec['model_deployment']}")
first_request = scenario_state["request_states"][0]
n_requests = len(scenario_state["request_states"])
print(f'{n_requests=}')
rich.print('first_request = ' + ub.urepr(first_request, nl=-2))
first_completion = first_request["result"]["completions"][0]["text"]
print(f"first_completion={first_completion!r}")

rich.print(interesting_stats)

PY


# Test on a bigger narrative qa dataset
export AUDIT_STORE_ROOT="${AUDIT_STORE_ROOT:-/data/crfm-helm-audit-store}"
export QWEN35_BUNDLE_ROOT="$AUDIT_STORE_ROOT/local-bundles/qwen35_vllm"
export MATERIALIZE_OUT="$QWEN35_BUNDLE_ROOT/smoketest/narrative"
python -m magnet.backends.helm.cli.materialize_helm_run \
  --run-entry "narrative_qa:model=qwen/qwen3.5-9b,data_augmentation=canonical" \
  --suite "audit-qwen35-materialize-smoke" \
  --max-eval-instances 10000 \
  --out-dpath "$MATERIALIZE_OUT" \
  --mode force_recompute \
  --local-path prod_env \
  --model-deployments-fpath "$QWEN35_BUNDLE_ROOT/model_deployments.yaml"



python - <<'PY'
import json
import os
import ubelt as ub
from pathlib import Path

materialize_out = Path(os.environ['MATERIALIZE_OUT'])
adapter_manifest_fpath = materialize_out / "adapter_manifest.json"
adapter_manifest = json.loads(adapter_manifest_fpath.read_text())
run_dpath = Path(adapter_manifest["computed"]["computed_run_dir"])
print(f"run_dpath={run_dpath}")

from magnet.backends.helm import helm_outputs
run = helm_outputs.HelmRun.coerce(run_dpath)

import rich
stats_df = run.dataframe.stats()
flags = stats_df['stats.name.name'].apply(lambda x: x in {"exact_match", "logprob", "num_completion_tokens"})
interesting_stats = stats_df[flags]
interesting_stats = interesting_stats.prefix_subframe('stats', drop_prefix=True)

stats = run.json.stats()
per_instance_stats = run.json.per_instance_stats()
scenario_state = run.json.scenario_state()

adapter_spec = scenario_state["adapter_spec"]
print(f"model={adapter_spec['model']}")
print(f"model_deployment={adapter_spec['model_deployment']}")
first_request = scenario_state["request_states"][0]
n_requests = len(scenario_state["request_states"])
print(f'{n_requests=}')
rich.print('first_request = ' + ub.urepr(first_request, nl=-2))
first_completion = first_request["result"]["completions"][0]["text"]
print(f"first_completion={first_completion!r}")

rich.print(interesting_stats.to_string())

PY

