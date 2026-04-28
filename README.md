# eval_audit

`eval_audit` is the workflow around HELM benchmark *audit* runs: indexing
the public HELM corpus, running local reproductions, comparing local vs.
public results at instance and metric level, and writing publication-quality
report bundles.

The recent (2026 Q1–Q2) line of work has been almost entirely on the
**analysis side** — composing virtual-experiment slices over already-existing
audit runs and producing reproducibility reports. The execution side
(scheduling new local HELM runs through `kwdagger`, launching vLLM/KubeAI
serving stacks, building manifests from scratch) **has not been exercised in
months** and is marked **UNSURE / not recently tested** below. Code paths still
exist; whether they still run end-to-end is unverified.

> If you only want the active path, jump to [Analysis runbooks](#analysis-runbooks-actively-maintained).

## What lives where

```
eval_audit/                 the Python package (renamed from helm_audit on 2026-04-28)
├── cli/                    argparse entrypoints — most CLIs are thin wrappers
├── workflows/              end-to-end sequencing (analyze, index, build summary, …)
├── reports/                pair report, core metrics, aggregate summary, paper labels
├── virtual/                virtual-experiment composer (recent, actively maintained)
├── normalized/             normalized comparison layer (EEE-aware)
├── planning/               comparison-intent planner used by core metrics
├── manifests/              manifest builders / presets  [not recently exercised]
├── helm/                   HELM-specific readers + diff helpers (analysis.py, diff.py,
│                           hashers.py, metrics.py, run_entries.py)
├── indexing/               run-spec hash + schema helpers
├── infra/                  paths, env, yaml IO, logging, plotly env
├── integrations/           kwdagger_bridge.py + vllm_service/  [not recently exercised]
├── compat/                 backward-compat shims
└── model_registry.py
```

External directories the workflow depends on:

- `reproduce/` — runbooks; one folder per scenario. Most are execution-shaped
  shell sequences (`00_check_env`, `10_make_manifest`, `20_run`, `30_compare`)
  and are **UNSURE** as of 2026-04. The two **analysis-only** runbooks at
  [`reproduce/pythia_mmlu_stress/`](reproduce/pythia_mmlu_stress/) and
  [`reproduce/open_helm_models_reproducibility/`](reproduce/open_helm_models_reproducibility/)
  *are* known-good — those are what the recent commits exercise.
- `configs/` — checked-in manifests and overrides only; generated state lives
  outside the repo.
- `docs/` — supporting docs. Several are **STALE** and need triage; see
  [Documentation status](#documentation-status) below.
- `reports/` — small generated artifacts that are still useful in-repo
  (`reports/filtering/`, `reports/core-run-analysis/`,
  `reports/aggregate-summary/`).

The big mutable working tree is on the data store, not in the repo:

```
$AUDIT_STORE_ROOT  (default: /data/crfm-helm-audit-store)
├── configs/                    generated run_specs.yaml, manifests/, run_details.yaml
├── indexes/                    audit_results_index_*.csv|jsonl|txt + official index
├── eee/local/<exp>/<run>/      EEE-converted local audit artifacts
├── crfm-helm-public-eee-test/  EEE-converted public HELM corpus (stress sweep)
├── analysis/                   per-experiment analysis (core-reports, eee-readiness, …)
├── virtual-experiments/<exp>/  virtual-experiment composition outputs
└── local-bundles/              per-bundle deployment YAMLs / process_context

$AUDIT_RESULTS_ROOT  (default: /data/crfm-helm-audit)
└── <experiment>/helm/helm_id_<hash>/...   raw local HELM run outputs
```

## Analysis runbooks (actively maintained)

These are what the 2026 Q1–Q2 commits exercise. They consume already-existing
audit runs and produce reproducibility reports. **No model is run; no
benchmark is downloaded.**

```bash
# Pythia × MMLU slice — 5 subjects, 5 packets, 4,536 instances
./reproduce/pythia_mmlu_stress/compose.sh
./reproduce/pythia_mmlu_stress/build_summary.sh

# Wider open-weight × benchmark slice — 121 packets, 431,605 instances
./reproduce/open_helm_models_reproducibility/compose.sh
./reproduce/open_helm_models_reproducibility/build_summary.sh
```

Each runbook is a thin wrapper over `eval-audit-build-virtual-experiment`
and `eval-audit-build-summary`, working from a checked-in YAML manifest at
`configs/virtual-experiments/<name>.yaml`. Outputs land at
`$AUDIT_STORE_ROOT/virtual-experiments/<name>/`.

The corresponding reproducibility narratives are in
[`reproduce/pythia_mmlu_stress/REPRODUCIBILITY_REPORT.md`](reproduce/pythia_mmlu_stress/REPRODUCIBILITY_REPORT.md)
and
[`reproduce/open_helm_models_reproducibility/REPRODUCIBILITY_REPORT.md`](reproduce/open_helm_models_reproducibility/REPRODUCIBILITY_REPORT.md).

The HELM-specific gotchas surfaced while building the comparison pipeline are
catalogued in [`docs/helm-gotchas.md`](docs/helm-gotchas.md) — that file is
current.

## Execution runbooks (UNSURE — not recently exercised)

These were the original framing of the project: schedule a local HELM run via
`kwdagger`, point HELM at a model deployment (vLLM, KubeAI, LiteLLM, or
HuggingFace), then compare. The Python and shell code still exists, but
**none of these scenarios have been exercised since the 2025 vLLM/KubeAI
work**. Treat them as historical reference, not as supported entry points.

| runbook | what it claims to do | status |
|---|---|---|
| `reproduce/smoke/` | minimal end-to-end sanity run | **UNSURE** |
| `reproduce/apples/` | apples-to-apples reproduction control | **UNSURE** |
| `reproduce/historic_grid/` | regenerate a historic public-run manifest grid | **UNSURE** |
| `reproduce/machine_compare/` | cross-machine indexing + pairwise comparison | **UNSURE** |
| `reproduce/qwen35_vllm/` | local vLLM smoke for `qwen/qwen3.5-9b` | **UNSURE** |
| `reproduce/qwen2_72b_vllm/` | vLLM smoke + EWOK historic grid for qwen2-72b | **UNSURE** |
| `reproduce/gpt_oss_20b_vllm/` | LiteLLM-fronted vLLM batch for gpt-oss-20b | **UNSURE** |
| `reproduce/small_models_kubeai/` | KubeAI overnight batch (qwen2.5-7b + vicuna-7b) | **UNSURE** |
| `reproduce/setup/` | one-time host setup scripts | **UNSURE** but harmless |

Re-validating any of these is its own piece of work — the assumptions in
their READMEs (server URLs, KubeAI namespaces, LiteLLM keys, deployment YAML
shape) drift fast. Pick one, run it, and update its README before claiming
it's still good.

## CLI

Entry points are declared in [`pyproject.toml`](pyproject.toml#L42). Active /
dormant breakdown:

**Active (exercised by the analysis runbooks):**

- `eval-audit-build-virtual-experiment` — compose a virtual-experiment slice from a YAML manifest
- `eval-audit-build-summary` — build the publication surface (sankeys, prioritized examples, coverage matrix, README)
- `eval-audit-analyze-experiment` — per-experiment analysis (delegates to packet planner + core metrics)
- `eval-audit-analyze-many` — batched experiment analysis
- `eval-audit-analyze-index-snapshot` — snapshot the audit-results index
- `eval-audit-rebuild-core` — rebuild the per-packet core metric report
- `eval-audit-report-core` / `eval-audit-report-aggregate` — single-packet and aggregate reporting
- `eval-audit-compare-pair` / `eval-audit-compare-batch` — pair-level comparison
- `eval-audit-index` — build the audit-results index
- `eval-audit-portfolio-status` — multi-experiment status snapshot
- `eval-audit-prepare-eee` — prepare EEE artifacts for downstream analysis

**UNSURE (execution-shaped; not recently exercised):**

- `eval-audit-check-env` — host-environment preflight (probably still works; light)
- `eval-audit-make-manifest` — generate execution manifests from run-spec selections
- `eval-audit-run` — preview/execute a kwdagger experiment from a manifest
  (default is preview; `--run=1` to execute)

`eval-audit-run` was originally the scheduling boundary. It still imports
cleanly but its kwdagger and HELM-execution side-effects haven't been
re-tested.

## Install

```bash
uv pip install -e .
```

Then the CLI scripts above are on `$PATH`. For analysis-only work this is
all you need.

For Plotly JPG/PNG sidecars on a headless Ubuntu 24.04 VM, install the Chrome
dependency once with
[`reproduce/setup/10_install_plotly_chrome_ubuntu2404.sh`](reproduce/setup/10_install_plotly_chrome_ubuntu2404.sh)
(also UNSURE — it has not been re-validated on the current images, but it's a
straightforward apt invocation).

## Documentation status

| file | status | note |
|---|---|---|
| [`docs/pipeline.md`](docs/pipeline.md) | **CURRENT** | rewritten 2026-04-28 to match the active EEE-driven analysis pipeline; the prior version is preserved at [`docs/historical/pipeline-pre-eee-refactor.md`](docs/historical/pipeline-pre-eee-refactor.md) |
| [`docs/helm-gotchas.md`](docs/helm-gotchas.md) | **CURRENT** | running ledger of HELM-specific behaviors hit during analysis |
| [`docs/helm-reproduction-research-journal.md`](docs/helm-reproduction-research-journal.md) | **CURRENT** | research context, failure taxonomies |
| [`docs/kwdagger-notes.md`](docs/kwdagger-notes.md) | **UNSURE** | small file, may still be accurate |
| [`docs/helm-null-completion-text-patch-proposal.md`](docs/helm-null-completion-text-patch-proposal.md) | **UNSURE** | pre-EEE patch proposal; outcome unclear |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | **PARTIALLY STALE** | core ADRs (raw vs derived, reports/, filesystem-as-interface) still hold; specific module/CLI lists drifted with the rename and recent refactors |

Moved into [`docs/historical/`](docs/historical/) on 2026-04-28 (preserved
verbatim — they may still be useful as records of *how* a problem was
approached at the time):

- `historical/pipeline-pre-eee-refactor.md` — the older end-to-end pipeline doc
- `historical/helm-reproduction-status-checkpoint.md`
- `historical/open-model-helm-reproduction-master-plan.md`
- `historical/reproduce-helm-session-v2.md`
- `historical/helm-reproduction-agent-brief.md`

## Caveats / things to verify before relying on a claim here

- **STALE** annotations above mean "I (the writer of this README on
  2026-04-28) couldn't quickly verify the file was still correct." It does
  not mean the file is wrong — only that nobody has confirmed it isn't.
- The `eval-audit-run` execution path still compiles and imports. It has not
  been *run* in months, so the kwdagger-side, vLLM-side, and
  manifest-building integration-test surface is **unverified**.
- The `crfm-helm-audit-store` and `crfm-helm-audit` data-store paths are
  preserved verbatim from the pre-rename world (HELM-the-benchmark naming);
  see [`docs/helm-gotchas.md`](docs/helm-gotchas.md).
- The `eval_audit_local` source-organization tag is the rename of
  `helm_audit_local`. Existing on-disk EEE artifacts that pre-date the rename
  still carry the old tag; see
  [`dev/oneoff/migrate_eee_source_org_tag.py`](dev/oneoff/migrate_eee_source_org_tag.py)
  to port them.
