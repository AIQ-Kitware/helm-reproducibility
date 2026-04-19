#!/usr/bin/env bash

small_models_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

resolve_kubeai_namespace() {
  if [[ -n "${KUBEAI_NAMESPACE:-}" ]]; then
    printf '%s\n' "$KUBEAI_NAMESPACE"
    return
  fi
  if command -v helm >/dev/null 2>&1; then
    local detected
    detected="$(helm list -A 2>/dev/null | awk 'NR>1 && $1=="kubeai" {print $2; exit}')"
    if [[ -n "$detected" ]]; then
      printf '%s\n' "$detected"
      return
    fi
  fi
  printf '%s\n' "default"
}

print_kubeai_diagnostics() {
  local namespace="$1"
  echo "=== kubectl -n $namespace get model -o wide ==="
  kubectl -n "$namespace" get model -o wide || true
  echo

  echo "=== kubectl -n $namespace describe model qwen2-5-7b-instruct-turbo-default ==="
  kubectl -n "$namespace" describe model qwen2-5-7b-instruct-turbo-default || true
  echo

  echo "=== kubectl -n $namespace describe model vicuna-7b-v1-3-no-chat-template ==="
  kubectl -n "$namespace" describe model vicuna-7b-v1-3-no-chat-template || true
  echo

  echo "=== kubectl -n $namespace get pods -o wide ==="
  kubectl -n "$namespace" get pods -o wide || true
  echo

  local kubeai_pods
  kubeai_pods="$(kubectl -n "$namespace" get pods --no-headers 2>/dev/null | awk '/kubeai/ {print $1}')"
  if [[ -n "$kubeai_pods" ]]; then
    local pod
    for pod in $kubeai_pods; do
      echo "=== kubectl -n $namespace logs $pod --tail=200 ==="
      kubectl -n "$namespace" logs "$pod" --tail=200 || true
      echo
    done
  elif kubectl -n "$namespace" get deploy kubeai >/dev/null 2>&1; then
    echo "=== kubectl -n $namespace logs deploy/kubeai --tail=200 ==="
    kubectl -n "$namespace" logs deploy/kubeai --tail=200 || true
    echo
  fi

  echo "=== kubectl -n $namespace get events --sort-by=.metadata.creationTimestamp | tail -n 40 ==="
  kubectl -n "$namespace" get events --sort-by=.metadata.creationTimestamp | tail -n 40 || true
}

wait_for_model_objects() {
  local namespace="$1"
  local attempts="${2:-60}"
  local sleep_s="${3:-10}"
  local i
  for ((i=1; i<=attempts; i++)); do
    if kubectl -n "$namespace" get model qwen2-5-7b-instruct-turbo-default >/dev/null 2>&1 && \
       kubectl -n "$namespace" get model vicuna-7b-v1-3-no-chat-template >/dev/null 2>&1; then
      echo "Both KubeAI Model objects exist in namespace $namespace"
      return 0
    fi
    echo "Waiting for KubeAI Model objects ($i/$attempts)..."
    sleep "$sleep_s"
  done
  return 1
}

wait_for_model_pods_ready() {
  local namespace="$1"
  local attempts="${2:-60}"
  local sleep_s="${3:-10}"
  local patterns='qwen2-5-7b-instruct-turbo-default|vicuna-7b-v1-3-no-chat-template'
  local i
  for ((i=1; i<=attempts; i++)); do
    local pod_lines
    pod_lines="$(kubectl -n "$namespace" get pods --no-headers 2>/dev/null | grep -E "$patterns" || true)"
    if [[ -n "$pod_lines" ]]; then
      local qwen_ready=0
      local vicuna_ready=0
      while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        local pod ready status
        pod="$(awk '{print $1}' <<<"$line")"
        ready="$(awk '{print $2}' <<<"$line")"
        status="$(awk '{print $3}' <<<"$line")"
        if [[ "$pod" == *qwen2-5-7b-instruct-turbo-default* && "$status" == "Running" && "${ready%/*}" == "${ready#*/}" ]]; then
          qwen_ready=1
        fi
        if [[ "$pod" == *vicuna-7b-v1-3-no-chat-template* && "$status" == "Running" && "${ready%/*}" == "${ready#*/}" ]]; then
          vicuna_ready=1
        fi
      done <<<"$pod_lines"
      if [[ "$qwen_ready" == "1" && "$vicuna_ready" == "1" ]]; then
        echo "Serving pods for both models are Ready"
        return 0
      fi
    fi
    echo "Waiting for serving pods to become Ready ($i/$attempts)..."
    sleep "$sleep_s"
  done
  return 1
}
