# pythia × MMLU/BoolQ — EEE-only smoke

The EEE-only counterpart to [`reproduce/pythia12b_mmlu_smoke/`](../pythia12b_mmlu_smoke/).

That runbook executes the dormant `eval-audit-run → kwdagger → magnet → helm-run`
chain to *produce* fresh local HELM run dirs for `pythia-12b-v0`. **This
runbook does not run any model.** It assumes the EEE artifacts already
exist on disk and runs the comparison + report pipeline against them
(no HELM run dirs, no `run_spec.json`, no GPU).

## Why pythia-6.9b instead of pythia-12b-v0?

The original smoke runbook targets `eleutherai/pythia-12b-v0`. On the
machine this runbook lives on, `pythia-12b-v0` HELM artifacts have not
been EEE-converted yet. Available EEE artifacts cover `pythia-6.9b` on
MMLU `us_foreign_policy` (`audit-mmlu-usfp-pythia-r{1,2}`) and BoolQ
(`audit-boolq-pythia-r{1,2}`), so this runbook uses those. The shape of
the comparison is identical; the model and benchmarks are what's
available.

## What this exercises

For each `(benchmark, model)` pair:

- 1 official EEE artifact (from `crfm-helm-public-eee-test/classic/v0.3.0/...`)
- 2 local EEE artifacts (`...-r1` and `...-r2`)

So the planner produces:

| (model, benchmark) | comparisons |
|---|---|
| `eleutherai/pythia-6.9b` × MMLU `us_foreign_policy` | 2× `official_vs_local` + 1× `local_repeat` |
| `eleutherai/pythia-6.9b` × BoolQ | 2× `official_vs_local` + 1× `local_repeat` |

The two `official_vs_local` per benchmark answer "did the local
reproduction match the public reference?" The single `local_repeat`
per benchmark answers "are the two local attempts repeatable
against each other?".

## How to run

```bash
./00_check_artifacts.sh   # verify the source EEE artifacts exist
./10_link_tree.sh         # build the from_eee-shaped symlink tree
./20_run.sh               # eval-audit-from-eee + aggregate summary
```

Each step is idempotent. Override the output location with:

```bash
OUT_ROOT=/some/other/dir ./10_link_tree.sh
OUT_ROOT=/some/other/dir ./20_run.sh
```

The default `OUT_ROOT` is `$AUDIT_STORE_ROOT/eee-only-smoke` (i.e.
outside the repo, on the audit-store filesystem with plenty of free
space).

## What lands

```
$OUT_ROOT/
├── eee_artifacts/                       # symlink tree (10_link_tree.sh)
│   ├── official/<benchmark>/<dev>/<model>/<uuid>.{json,_samples.jsonl}
│   └── local/<experiment>/<benchmark>/<dev>/<model>/<uuid>.{json,_samples.jsonl}
└── from_eee_out/                        # analysis outputs (20_run.sh)
    ├── audit_results_index.latest.csv
    ├── official_public_index.latest.csv
    ├── planning/
    ├── <experiment>/core-reports/<packet>/core_metric_report.latest.{txt,json,png}
    └── aggregate-summary/all-results/
        ├── README.latest.txt
        ├── agreement_curve.latest.{html,jpg}
        └── reproducibility_buckets.latest.{html,jpg}
```

## What's *not* answered, and why

For EEE-only inputs, several comparability facts collapse to
`status=unknown`:

- `same_scenario_class`
- `same_benchmark_family`
- `same_deployment`
- `same_instructions`
- `same_max_eval_instances`

These need HELM `run_spec.json`, which is not part of the EEE artifact
shape. They surface as `comparability_unknown:*` warnings in
`warnings.latest.json` per packet. Agreement metrics (run-level and
instance-level abs-delta, agreement curves, per-metric breakdowns) are
unaffected — those come from the EEE artifacts themselves.

If you want those facts evaluated for this runbook, drop the source
HELM `run_spec.json` next to the EEE aggregate and re-run; both
`from_eee` and `compare-pair-eee` auto-detect the sidecar. See
[`docs/eee-vs-helm-metadata.md`](../../docs/eee-vs-helm-metadata.md).

## Compared to the HELM-driven smoke

| | `pythia12b_mmlu_smoke` (HELM) | `pythia_smoke_eee_only` (this) |
|---|---|---|
| Model | `eleutherai/pythia-12b-v0` | `eleutherai/pythia-6.9b` |
| Runs HELM execution chain? | yes (kwdagger → magnet → helm-run) | no |
| Needs GPU? | yes | no |
| Needs HF download? | yes (model weights) | no |
| Comparability facts | full | 5 collapse to `unknown` (without sidecar) |
| Agreement metrics | full | full |
| Output shape | core_metric_report.* + aggregate summary | core_metric_report.* + aggregate summary |

The two runbooks are complementary: the first proves the *execution*
side still works on this machine; this one proves the *analysis* side
works against pre-existing EEE artifacts.
