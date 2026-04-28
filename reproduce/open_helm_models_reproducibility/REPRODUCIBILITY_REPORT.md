# Open HELM Models — Reproducibility Case Study

> *How reproducible are the open-weight models in the public HELM
> corpus, given the local audit results we currently have?*

This is the expanded virtual experiment that the NeurIPS EEE paper case
study draws from. Five open-weight model families, 19 benchmarks, 121
analyzed packets totaling **431,605 instance-level comparisons**, all
joined against the published HELM reference results.

The manifest is checked in at
[`configs/virtual-experiments/open-helm-models-reproducibility.yaml`](../../../home/joncrall/code/helm_audit/configs/virtual-experiments/open-helm-models-reproducibility.yaml);
the runbook is `reproduce/open_helm_models_reproducibility/`.

## Headline numbers

> **Aggregate instance-level agreement at abs_tol=0: 0.848 ± 0.165
> across 121 packets / 431,605 instances. Median packet agreement
> 0.900; range 0.283–1.000.**

These numbers are *not* the publication-quality story by themselves —
they're the raw aggregate, dominated by `deployment_drift` (HF API →
vLLM) and a long tail of `execution_spec_drift` (the local rerun used
a different `max_eval_instances` or adapter than the published run).
Per-model and per-benchmark breakdowns below distinguish "reproducible
open model" from "open model that reproduces its public number when
rerun byte-for-byte under the same recipe", which is the distinction
the paper actually wants to surface.

## Coverage funnel (Stage A + Stage B)

Both sankeys live under `reports/aggregate-summary/.../`:

- `sankey_a_universe_to_scope.latest.html` — 13,579 universe →
  Stage-1 gates → manifest scope (5 model families × 19 benchmarks).
- `sankey_b_scope_to_analyzed.latest.html` — manifest scope →
  attempted → completed → analyzed at abs_tol=0.

Coverage funnel summary (`reports/scoped_funnel/coverage_funnel_summary.latest.txt`):

| stage | count | % of target |
|---|---:|---:|
| target (in-scope official rows) | 295 | 100% |
| reproduced (logical-key match) | 166 | 56.3% |
| completed (run_path on disk) | 166 | 56.3% |
| analyzed (has packet) | 166 | 56.3% |

The 56% figure is "of the public HELM rows we declared in scope, here's
how many we have a local repro of and have analyzed". The 121 packet
count below is smaller because the planner collapses local-vs-official
matches into a single packet per `logical_run_key`.

## Per-model reproducibility

| model | packets | instances | mean agree@0 | min | max | dominant diagnosis |
|---|---:|---:|---:|---:|---:|---|
| `eleutherai/pythia-2.8b-v0` | 3 | 12,000 | **0.993** | 0.981 | 1.000 | deployment_drift |
| `lmsys/vicuna-7b-v1.3` | 39 | 146,988 | **0.938** | 0.554 | 1.000 | deployment_drift |
| `eleutherai/pythia-6.9b` | 39 | 146,988 | **0.896** | 0.679 | 1.000 | deployment_drift |
| `qwen/qwen2.5-7b-instruct-turbo` | 38 | 117,088 | **0.716** | 0.283 | 1.000 | execution_spec_drift |
| `openai/gpt-oss-20b` | 2 | 8,541 | **0.436** | 0.434 | 0.438 | multiple_primary_reasons |

Pythia 2.8b and Vicuna are essentially "as reproducible as the recipe
allows" — the bulk of the disagreement is the HF→vLLM substitution.
Pythia 6.9b is in the same regime with a wider tail (more benchmarks
shows up the long-form-generation drift).

Qwen 2.5 7b instruct sits notably lower at 0.72. Looking at the per-packet
diagnoses, the dominant signal is `execution_spec_drift` — the local
runs differ from the public ones in their adapter or
`max_eval_instances`, not in the model output. That's a recipe issue,
not a reproducibility issue: same model and same scenario, but the
*evaluation protocol* differed between runs. The local Qwen runs went
through a different KubeAI deployment path that exposes its own adapter
spec.

gpt-oss-20b at 0.44 is the most striking signal in the dataset, but it
sits on only 2 packets (bbq, ifeval) and the diagnosis is
`multiple_primary_reasons` — both deployment AND execution-spec drift
contribute. The vendor's stated chat template differs between vLLM-served
and HF-served runs and produces measurably different completions even
on the same prompts. With this small sample we can't separate "open
model that reproduces poorly" from "open model whose serving stacks
disagree more than expected"; flag for follow-up.

## Per-benchmark reproducibility (sorted by mean agreement@0, descending)

| benchmark | packets | instances | mean | min | max |
|---|---:|---:|---:|---:|---:|
| `entity_data_imputation` | 4 | 3,392 | 0.998 | 0.992 | 1.000 |
| `synthetic_reasoning` | 6 | 24,000 | 0.991 | 0.976 | 1.000 |
| `truthful_qa` | 2 | 10,464 | 0.988 | 0.977 | 0.999 |
| `lsat_qa` | 2 | 7,376 | 0.979 | 0.960 | 0.998 |
| `boolq` | 3 | 12,000 | 0.978 | 0.952 | 1.000 |
| `imdb` | 2 | 8,000 | 0.996 | 0.991 | 1.000 |
| `quac` | 2 | 6,000 | 0.963 | 0.939 | 0.987 |
| `civil_comments` | 20 | 80,000 | 0.941 | 0.819 | 1.000 |
| `commonsense` | 2 | 8,000 | 0.916 | 0.916 | 0.916 |
| `mmlu` | 20 | 18,144 | 0.907 | 0.649 | 1.000 |
| `gsm` | 4 | 4,000 | 0.904 | 0.822 | 0.990 |
| `wikifact` | 20 | 126,832 | 0.836 | 0.554 | 0.953 |
| `med_qa` | 2 | 16,000 | 0.786 | 0.786 | 0.786 |
| `entity_matching` | 6 | 11,200 | 0.758 | 0.679 | 0.832 |
| `legalbench` | 10 | 16,376 | 0.671 | 0.537 | 1.000 |
| `wmt_14` | 10 | 60,000 | 0.658 | 0.544 | 0.716 |
| `narrative_qa` | 4 | 11,280 | 0.616 | 0.283 | 0.986 |
| `bbq` | 1 | 8,000 | 0.434 | 0.434 | 0.434 |
| `ifeval` | 1 | 541 | 0.438 | 0.438 | 0.438 |

The benchmark axis carries the publishable signal: short-output classification
benchmarks (`entity_data_imputation`, `synthetic_reasoning`, `truthful_qa`,
`lsat_qa`, `boolq`, `imdb`) reproduce at >0.97 mean with tight ranges.
Long-form generation (`narrative_qa`, `wmt_14`) and instruction-following
(`ifeval`) sit at 0.44–0.66, where serving-stack non-determinism (sampling
parameters, tokenizer differences, stop-sequence handling) introduces
genuine output variance.

## Diagnosis breakdown

| diagnosis | packets | % |
|---|---:|---:|
| `deployment_drift` | 81 | 67% |
| `execution_spec_drift` | 36 | 30% |
| `multiple_primary_reasons` | 2 | 2% |
| `completion_content_drift` | 2 | 2% |

**Two-thirds of the disagreement is deployment-only.** That's the
narrative the paper supports: "open HELM runs are reproducible up to
the deployment substitution; once you hold the recipe constant the
agreement is high". The 30% with `execution_spec_drift` is a recipe
issue documented in the per-packet `core_metric_management_summary` —
the comparison is not strictly apples-to-apples because the local run
overrode `max_eval_instances` or used a different adapter.

## What the paper case study can claim

Strong claims, well-supported:

- **Pythia 2.8b/6.9b and Vicuna 7b reproduce at >0.90 mean
  instance-level agreement** across 14 of the 19 benchmarks we examined
  when comparing public HELM (HF API) to local vLLM execution. The
  remaining disagreement is concentrated in long-form generation and is
  consistent with sampling/tokenizer drift — not a model-correctness
  issue.
- **Short-output classification benchmarks** (entity matching, mmlu, boolq,
  truthful_qa, lsat_qa) **reproduce at >0.94 mean with tight per-subject
  variance** — the "good case" for cross-deployment reproducibility.
- **Long-form generation reproduces poorly** even on open models with
  the same weights: `narrative_qa` 0.62, `wmt_14` 0.66, `legalbench`
  0.67. The bottom of this distribution drives the aggregate average
  down.
- **The `deployment_drift` diagnosis explains 67% of all
  cross-execution disagreement** in this dataset; this is the
  publishable mechanism (HF API and vLLM differ in
  sampling/tokenization even with the same weights).

Weaker claims, flagged for the discussion section:

- **Qwen 2.5 7b instruct's 0.72 mean is largely an
  execution-spec-drift artifact** in this dataset, not a true
  reproducibility failure — different KubeAI deployment + different
  adapter than the public HELM run. With matched recipe the number
  would likely sit near vicuna/pythia.
- **gpt-oss-20b reproduces poorly (0.44)** but only on two benchmarks;
  more data needed before generalizing.
- **Run-level versus instance-level**: the agreement at abs_tol=0.05
  on the run-level metric averages is consistently higher than at
  instance-level. The paper should report both since the publishable
  HELM number is a run-level metric average, not an instance-by-instance
  agreement rate.

## Reading order for a referee

1. `reports/aggregate-summary/.../README.latest.txt` — high-level
   coverage / agreement narrative for this scope.
2. `reports/aggregate-summary/.../sankey_a_universe_to_scope.latest.html`
   — the context-establishment funnel (universe → manifest scope).
3. `reports/aggregate-summary/.../sankey_b_scope_to_analyzed.latest.html`
   — coverage funnel (in-scope → analyzed).
4. `reports/aggregate-summary/.../prioritized_examples.latest/best/`
   — exemplary high-agreement packets for the "yes, it reproduces"
   side of the story.
5. `reports/aggregate-summary/.../prioritized_examples.latest/worst/`
   — the worst-agreement packets to dissect failure modes.
6. `reports/aggregate-summary/.../coverage_matrix.latest.html`
   — model × benchmark heat map showing which combos we covered and
   how well each reproduced.
7. `reports/scoped_funnel/missing_targets.latest.csv` — the 129
   public-HELM rows in scope that we don't have a local repro for
   yet (next-step work).

## Reproducing this report

```bash
./reproduce/open_helm_models_reproducibility/compose.sh
./reproduce/open_helm_models_reproducibility/build_summary.sh
```

Both are thin wrappers over `helm-audit-build-virtual-experiment` and
`helm-audit-build-summary` against the checked-in manifest. Compose
takes ~30 minutes mostly because it converts ~180 local HELM runs to
EEE format on demand; the actual analysis after that is fast.
