# Pythia × MMLU stress test (virtual experiment)

A *virtual experiment*: a declarative slice over already-executed audit
runs and matching public HELM rows, scoped to Pythia models on MMLU
subjects. There is no execution step in this runbook — it operates
entirely on artifacts that already exist on disk.

The manifest is checked in at
[`configs/virtual-experiments/pythia-mmlu-stress.yaml`](../../configs/virtual-experiments/pythia-mmlu-stress.yaml).

## What this assumes

- The local audit-results index exists at
  `$AUDIT_STORE_ROOT/indexes/audit_results_index.latest.csv`.
- The official-public-HELM index exists at
  `$AUDIT_STORE_ROOT/indexes/official_public_index.latest.csv`.
- The source experiments listed in the manifest's
  `sources[].include_experiments` (`audit-mmlu-usfp-pythia-r1`,
  `audit-mmlu-usfp-pythia-r2`, `audit-historic-grid`) have actually
  been executed and indexed. If they haven't, the composed slice is
  empty and the runbook short-circuits.
- The official EEE conversion is done (sweep DB at
  `$AUDIT_STORE_ROOT/crfm-helm-public-eee-test/sweep_index.db`); local
  HELM→EEE conversions for the matched run-specs are produced on demand.

A future revision of this folder should add a `recompute.sh` step that
schedules+executes any missing source runs before composition. That work
is **not yet done** — for now, this runbook is *analysis-and-publication
only*.

## Steps

```
./compose.sh           # filter sources, run analyze_experiment per packet
./build_summary.sh     # build aggregate sankeys / agreement curves / README
```

`compose.sh` and `build_summary.sh` are independently re-runnable.
Re-render plots without rebuilding everything by running
`redraw_plots.sh` inside any individual core-report directory under
`<output_root>/analysis/core-reports/`.

## Output layout

The manifest's `output.root` (default
`$AUDIT_STORE_ROOT/virtual-experiments/pythia-mmlu-stress`) is the only
place this runbook writes:

```
<output_root>/
├── manifest.yaml                       (snapshot of what was composed with)
├── provenance.json                     (rows-seen / rows-retained per source, external_eee inventory)
├── indexes/
│   ├── audit_results_index.csv         (synthesized local slice, virtual experiment_name stamped, source_experiment_name preserved)
│   └── official_public_index.csv       (synthesized official slice)
├── analysis/
│   ├── planning/                       (comparison_intents, packets, components, warnings)
│   ├── core-reports/<one per packet>/  (per-packet core_metric report)
│   ├── experiment_summary.latest.{json,csv,txt}
│   └── reproduce.latest.sh
└── reports/
    └── aggregate-summary/<scope>/      (story-arc sankeys, agreement curve, prioritized examples, README)
```

## Env vars

| var | default | purpose |
|---|---|---|
| `AUDIT_STORE_ROOT` | `/data/crfm-helm-audit-store` | indexes + EEE artifact roots |
| `MANIFEST_FPATH` | `configs/virtual-experiments/pythia-mmlu-stress.yaml` | which manifest to build |
| `PYTHON_BIN` | `python` | interpreter (point at your venv) |

## Adding Inspect AI (or other external) EEE artifacts

The manifest format accepts `sources[].kind=external_eee` entries with
`components: [...]`. They are parsed and recorded in `provenance.json`
today; the planner does not yet consume them. When that's wired in, no
manifest change is required — the existing entries become first-class
report components alongside the local and official ones.
