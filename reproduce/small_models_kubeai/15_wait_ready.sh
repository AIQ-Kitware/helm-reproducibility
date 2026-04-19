#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/reproduce/small_models_kubeai/_lib.sh"

KUBEAI_NAMESPACE="$(resolve_kubeai_namespace)"
KUBEAI_BASE_URL="${KUBEAI_BASE_URL:-http://127.0.0.1:8000/openai/v1}"
READINESS_ATTEMPTS="${READINESS_ATTEMPTS:-60}"
READINESS_SLEEP_SECONDS="${READINESS_SLEEP_SECONDS:-10}"

cleanup_on_fail() {
  local exit_code=$?
  if [[ $exit_code -ne 0 ]]; then
    echo
    echo "Readiness checks failed; printing KubeAI diagnostics"
    print_kubeai_diagnostics "$KUBEAI_NAMESPACE"
  fi
  exit "$exit_code"
}
trap cleanup_on_fail EXIT

wait_for_model_objects "$KUBEAI_NAMESPACE" "$READINESS_ATTEMPTS" "$READINESS_SLEEP_SECONDS"
wait_for_model_pods_ready "$KUBEAI_NAMESPACE" "$READINESS_ATTEMPTS" "$READINESS_SLEEP_SECONDS"

retry_http_check() {
  local label="$1"
  local url="$2"
  local payload="$3"
  local attempts="$4"
  local sleep_s="$5"
  local i
  for ((i=1; i<=attempts; i++)); do
    echo "Checking $label ($i/$attempts)..."
    local curl_args=(-fsS "$url")
    if [[ -n "$payload" ]]; then
      curl_args+=(-H 'Content-Type: application/json' -d "$payload")
    fi
    if curl "${curl_args[@]}"; then
      echo
      return 0
    fi
    echo
    sleep "$sleep_s"
  done
  return 1
}

retry_models_list() {
  local attempts="$1"
  local sleep_s="$2"
  local i
  for ((i=1; i<=attempts; i++)); do
    echo "Checking OpenAI-compatible /models ($i/$attempts)..."
    local response
    if response="$(curl -fsS "$KUBEAI_BASE_URL/models")"; then
      printf '%s\n' "$response"
      if printf '%s' "$response" | python3 -c 'import json,sys; data=json.load(sys.stdin); ids={item.get("id") for item in data.get("data", [])}; sys.exit(0 if {"qwen2-5-7b-instruct-turbo-default","vicuna-7b-v1-3-no-chat-template"} <= ids else 1)'; then
        echo "Both public model ids are present in /models"
        return 0
      fi
    fi
    echo
    sleep "$sleep_s"
  done
  return 1
}

retry_models_list "$READINESS_ATTEMPTS" "$READINESS_SLEEP_SECONDS"

retry_http_check \
  "Qwen chat completion" \
  "$KUBEAI_BASE_URL/chat/completions" \
  '{
    "model": "qwen2-5-7b-instruct-turbo-default",
    "messages": [{"role": "user", "content": "Reply with the word ready."}],
    "max_tokens": 16
  }' \
  "$READINESS_ATTEMPTS" \
  "$READINESS_SLEEP_SECONDS"

retry_http_check \
  "Vicuna completions" \
  "$KUBEAI_BASE_URL/completions" \
  '{
    "model": "vicuna-7b-v1-3-no-chat-template",
    "prompt": "Reply with the word ready.",
    "max_tokens": 16
  }' \
  "$READINESS_ATTEMPTS" \
  "$READINESS_SLEEP_SECONDS"

trap - EXIT
echo "Both KubeAI models are responding at $KUBEAI_BASE_URL"
