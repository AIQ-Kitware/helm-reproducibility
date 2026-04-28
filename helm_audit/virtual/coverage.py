"""Stage-B coverage funnel for a virtual experiment.

Given a composed virtual experiment (filtered target + filtered local rows
+ external EEE components) and the post-analysis rows on disk, compute the
``Scope -> Reproduced -> Completed -> Analyzed`` funnel and emit the
sankey + summary artifacts that go with it.

The artifacts are deliberately named with ``b_`` prefix and a vocabulary
that fits the broader four-stage frame:

    Universe -> Scope -> Reproduced -> Completed -> Analyzed

so a future Stage-A pass (Universe -> Scope) slots in cleanly without a
rename. The composed virtual experiment already encodes the
``Universe -> Scope`` step in its ``provenance.json`` rows-discarded
counts, so a Stage-A artifact can be derived later from that without
changing Stage-B behavior.

Two coverage views are emitted in parallel:

  * **logical** (default narrative): join target and local rows on
    ``logical_run_key`` (run-spec ignoring suite_version). Optimistic but
    matches the research story — "we have a repro for this run-spec".
  * **versioned** (sidecar): join on ``(logical_run_key, suite_version)``
    so a target row only counts as reproduced if a local row matches that
    specific public-track version.
"""
from __future__ import annotations

import csv
import dataclasses
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from helm_audit.helm.hashers import stable_hash36
from helm_audit.infra.fs_publish import (
    safe_unlink,
    stamped_history_dir,
    write_latest_alias,
)
from helm_audit.utils import sankey_builder
from helm_audit.utils.sankey import emit_sankey_artifacts


# ---------------------------------------------------------------------------
# Dimension parsing helpers (shared with virtual.compose; re-derive here so
# the coverage step has no upstream dependency on a particular index schema).
# ---------------------------------------------------------------------------

_BENCHMARK_PREFIX_RE = re.compile(r"^([^:]+):")
_MODEL_KEY_RE = re.compile(r"(?:^|,)model=([^,]+)")


def _parse_benchmark(text: str | None) -> str | None:
    if not text:
        return None
    m = _BENCHMARK_PREFIX_RE.match(text)
    return m.group(1) if m else None


def _parse_model(text: str | None) -> str | None:
    if not text:
        return None
    m = _MODEL_KEY_RE.search(text)
    if not m:
        return None
    return m.group(1).replace("_", "/", 1)


def _row_dim(row: dict[str, Any], dim: str, *, source_kind: str) -> str:
    """Return a stringified dimension value for a row, with run_name fallback."""
    direct = (row.get(dim) or "").strip()
    if direct:
        return direct
    name = row.get("run_name") or row.get("logical_run_key") or ""
    if dim == "benchmark":
        return _parse_benchmark(name) or "unknown"
    if dim == "model":
        return _parse_model(name) or "unknown"
    if dim == "suite_version":
        return (row.get("suite_version") or "unknown")
    return "unknown"


def _logical_run_key(row: dict[str, Any]) -> str:
    return str(row.get("logical_run_key") or row.get("run_entry") or row.get("run_name") or "").strip()


def _short_alias_map(values: list[str], *, prefix: str = "v") -> dict[str, str]:
    """Build a deterministic short alias for each long label.

    Same shape as the ECDF-legend aliasing used in core_metrics: same
    label always maps to the same alias; no two distinct labels collide.
    Hash length auto-extends if the default 4 chars happens to collide.
    """
    unique = sorted(set(values))
    if not unique:
        return {}
    for hash_len in range(4, 33):
        candidate = {label: f"{prefix}{stable_hash36(label)[:hash_len]}" for label in unique}
        if len(set(candidate.values())) == len(candidate):
            return candidate
    # Pathological fall-through (sha256 base36 collisions are astronomically rare).
    return {label: f"{prefix}{stable_hash36(label)}_{i}" for i, label in enumerate(unique)}


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class TargetCoverageRow:
    """One target official row annotated with its coverage status."""
    logical_run_key: str
    run_name: str
    model: str
    benchmark: str
    suite_version: str
    public_track: str
    target_run_path: str | None
    # Coverage by logical key (version-collapsed):
    matched_logical: bool
    n_local_logical_matches: int
    # Coverage by (logical_key, suite_version):
    matched_versioned: bool
    n_local_versioned_matches: int
    # Downstream stage:
    has_completed_local: bool   # at least one logical-matched local row has a run_path on disk
    has_analyzed_local: bool    # at least one logical-matched local row has a packet/report
    example_local_run_paths: list[str]
    example_analyzed_report_dirs: list[str]


@dataclasses.dataclass
class CoverageReport:
    name: str
    description: str
    target_rows: list[TargetCoverageRow]
    n_target: int
    n_reproduced_logical: int
    n_reproduced_versioned: int
    n_completed: int
    n_analyzed: int
    by_dim: dict[str, list[dict[str, Any]]]
    missing: list[TargetCoverageRow]
    extra_local_keys: list[str]
    # When the local-side suite_version field doesn't carry a public-track
    # tag (e.g. local audits use experiment names like ``audit-historic-grid``
    # instead of ``v0.2.4``), the versioned join is structurally unable to
    # produce matches even when the underlying run_specs are identical.
    # Surface this so a reader doesn't read ``versioned=0`` as bad coverage.
    versioned_join_meaningful: bool


# ---------------------------------------------------------------------------
# Analysis-side discovery: which logical keys have an analyzed packet?
# ---------------------------------------------------------------------------


def _analyzed_logical_keys(analysis_root: Path) -> tuple[set[str], dict[str, list[str]]]:
    """Walk the experiment's analysis tree and return (analyzed_logical_keys, key->report_dirs).

    Reads each per-packet ``components_manifest.latest.json`` to get the
    ``run_entry`` (which doubles as the logical key for local rows).
    """
    analyzed: set[str] = set()
    examples: dict[str, list[str]] = defaultdict(list)
    if not analysis_root.is_dir():
        return analyzed, examples
    for components_fpath in analysis_root.rglob("core-reports/*/components_manifest.latest.json"):
        try:
            data = json.loads(components_fpath.read_text())
        except Exception:
            continue
        run_entry = (data.get("run_entry") or data.get("logical_run_key") or "").strip()
        if not run_entry:
            continue
        analyzed.add(run_entry)
        report_dpath = components_fpath.parent
        if len(examples[run_entry]) < 3:
            examples[run_entry].append(str(report_dpath))
    return analyzed, examples


# ---------------------------------------------------------------------------
# Core: compute coverage from compose result + analysis
# ---------------------------------------------------------------------------


def compute_coverage(
    *,
    name: str,
    description: str,
    target_rows: list[dict[str, Any]],
    local_rows: list[dict[str, Any]],
    analysis_root: Path,
    breakdown_dims: tuple[str, ...] = ("model", "benchmark", "suite_version"),
) -> CoverageReport:
    """Join target + local rows and compute the Stage-B coverage funnel."""
    # Bucket local rows by both join keys.
    local_by_logical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    local_by_versioned: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    versioned_meaningful = False
    public_version_re = re.compile(r"^v\d+\.\d+(\.\d+)?$")
    for row in local_rows:
        key = _logical_run_key(row)
        if not key:
            continue
        local_by_logical[key].append(row)
        # Prefer suite_version (public-track tag); fall back to suite. Only
        # treat the versioned join as meaningful if at least one local row
        # carries a public-track-style version (e.g. ``v0.2.4``).
        suite_version = (row.get("suite_version") or "").strip()
        suite = (row.get("suite") or "").strip()
        if suite_version and public_version_re.match(suite_version):
            version = suite_version
            versioned_meaningful = True
        elif suite and public_version_re.match(suite):
            version = suite
            versioned_meaningful = True
        else:
            version = suite_version or suite or "unversioned"
        local_by_versioned[(key, version)].append(row)

    analyzed_keys, analyzed_examples = _analyzed_logical_keys(analysis_root)

    annotated: list[TargetCoverageRow] = []
    for row in target_rows:
        logical = _logical_run_key(row)
        run_name = (row.get("run_name") or logical or "").strip()
        version = (row.get("suite_version") or "unversioned").strip() or "unversioned"
        local_logical_matches = local_by_logical.get(logical, [])
        local_versioned_matches = local_by_versioned.get((logical, version), [])
        completed = [
            (r.get("run_path") or r.get("run_dir") or "").strip()
            for r in local_logical_matches
        ]
        completed = [p for p in completed if p]
        analyzed_dirs = analyzed_examples.get(logical, [])
        # Local rows record run_entry with the canonical ``model=org/name`` form
        # (slash); the planner's logical_run_key uses underscored form. Try both.
        if not analyzed_dirs:
            for r in local_logical_matches:
                r_entry = (r.get("run_entry") or "").strip()
                if r_entry and r_entry in analyzed_keys:
                    analyzed_dirs = analyzed_examples.get(r_entry, [])
                    if analyzed_dirs:
                        break
        annotated.append(
            TargetCoverageRow(
                logical_run_key=logical,
                run_name=run_name,
                model=_row_dim(row, "model", source_kind="official"),
                benchmark=_row_dim(row, "benchmark", source_kind="official"),
                suite_version=version,
                public_track=(row.get("public_track") or "main").strip() or "main",
                target_run_path=(row.get("run_path") or row.get("public_run_dir") or None),
                matched_logical=bool(local_logical_matches),
                n_local_logical_matches=len(local_logical_matches),
                matched_versioned=bool(local_versioned_matches),
                n_local_versioned_matches=len(local_versioned_matches),
                has_completed_local=bool(completed),
                has_analyzed_local=bool(analyzed_dirs),
                example_local_run_paths=completed[:3],
                example_analyzed_report_dirs=analyzed_dirs[:3],
            )
        )

    target_logical_keys = {row.logical_run_key for row in annotated if row.logical_run_key}
    extra_local_keys = sorted(set(local_by_logical) - target_logical_keys)

    n_target = len(annotated)
    n_reproduced_logical = sum(1 for r in annotated if r.matched_logical)
    n_reproduced_versioned = sum(1 for r in annotated if r.matched_versioned)
    n_completed = sum(1 for r in annotated if r.has_completed_local)
    n_analyzed = sum(1 for r in annotated if r.has_analyzed_local)

    by_dim: dict[str, list[dict[str, Any]]] = {}
    for dim in breakdown_dims:
        groups: dict[str, dict[str, int]] = defaultdict(lambda: {
            "target": 0,
            "reproduced_logical": 0,
            "reproduced_versioned": 0,
            "completed": 0,
            "analyzed": 0,
        })
        for r in annotated:
            value = getattr(r, dim, "unknown")
            grp = groups[value]
            grp["target"] += 1
            if r.matched_logical:
                grp["reproduced_logical"] += 1
            if r.matched_versioned:
                grp["reproduced_versioned"] += 1
            if r.has_completed_local:
                grp["completed"] += 1
            if r.has_analyzed_local:
                grp["analyzed"] += 1
        by_dim[dim] = [
            {"value": value, **counts}
            for value, counts in sorted(groups.items())
        ]

    missing = [r for r in annotated if not r.matched_logical]

    return CoverageReport(
        name=name,
        description=description,
        target_rows=annotated,
        n_target=n_target,
        n_reproduced_logical=n_reproduced_logical,
        n_reproduced_versioned=n_reproduced_versioned,
        n_completed=n_completed,
        n_analyzed=n_analyzed,
        by_dim=by_dim,
        missing=missing,
        extra_local_keys=extra_local_keys,
        versioned_join_meaningful=versioned_meaningful,
    )


# ---------------------------------------------------------------------------
# Artifact emission
# ---------------------------------------------------------------------------


def _pct(num: int, denom: int) -> str:
    if denom <= 0:
        return "  n/a"
    return f"{100 * num / denom:5.1f}%"


def _format_summary(coverage: CoverageReport) -> list[str]:
    versioned_line = (
        f"  reproduced (versioned, key+suite_version):   "
        f"{coverage.n_reproduced_versioned:>5}  ({_pct(coverage.n_reproduced_versioned, coverage.n_target)} of target)"
        if coverage.versioned_join_meaningful
        else "  reproduced (versioned, key+suite_version):   "
        "  N/A  (local rows do not carry public-track suite_version tags;"
        " versioned join is structurally degenerate for this scope)"
    )
    lines = [
        f"Coverage Funnel — {coverage.name}",
        "=" * (18 + len(coverage.name)),
        f"description: {coverage.description}",
        "",
        "Stage B (Scope -> Reproduced -> Completed -> Analyzed):",
        f"  target            (in scope, official):       {coverage.n_target:>5}",
        f"  reproduced (logical, version-collapsed):     "
        f"{coverage.n_reproduced_logical:>5}  ({_pct(coverage.n_reproduced_logical, coverage.n_target)} of target)",
        versioned_line,
        f"  completed   (reproduced AND run_path exists): "
        f"{coverage.n_completed:>5}  ({_pct(coverage.n_completed, coverage.n_reproduced_logical)} of reproduced; "
        f"{_pct(coverage.n_completed, coverage.n_target)} of target)",
        f"  analyzed    (completed AND has packet):       "
        f"{coverage.n_analyzed:>5}  ({_pct(coverage.n_analyzed, coverage.n_completed)} of completed; "
        f"{_pct(coverage.n_analyzed, coverage.n_target)} of target)",
        "",
        "Note on join keys:",
        "  - logical (version-collapsed) is the primary narrative — \"we have a repro for this run-spec\"",
        "  - versioned makes a target row count as reproduced only if a local row matches its specific public-track version.",
        "",
    ]
    for dim, rows in coverage.by_dim.items():
        if not rows:
            continue
        lines.append(f"By {dim}:")
        header = f"  {dim:<32s} {'target':>7} {'reproduced':>11} {'completed':>10} {'analyzed':>9} {'%anal':>7}"
        lines.append(header)
        lines.append("  " + "-" * (len(header) - 2))
        for entry in rows:
            t = entry["target"]
            a = entry["analyzed"]
            lines.append(
                f"  {entry['value']:<32s} {t:>7d} {entry['reproduced_logical']:>11d} "
                f"{entry['completed']:>10d} {a:>9d} {_pct(a, t):>7}"
            )
        lines.append("")
    if coverage.missing:
        lines.append(f"Missing targets (no local repro): {len(coverage.missing)}")
        lines.append("  See missing_targets.latest.csv for the full list.")
        lines.append("")
    if coverage.extra_local_keys:
        lines.append(f"Local logical_run_keys not in target scope: {len(coverage.extra_local_keys)}")
        lines.append("  These are local rows whose run-spec is not in the manifest's scope.")
        lines.append("  (Usually empty for tightly-scoped virtual experiments.)")
        lines.append("")
    return lines


def _coverage_payload(coverage: CoverageReport) -> dict[str, Any]:
    return {
        "name": coverage.name,
        "description": coverage.description,
        "stage_a__universe_to_scope": None,  # populated by a future Stage-A pass
        "stage_b__scope_to_analyzed": {
            "n_target": coverage.n_target,
            "n_reproduced_logical": coverage.n_reproduced_logical,
            "n_reproduced_versioned": coverage.n_reproduced_versioned,
            "n_completed": coverage.n_completed,
            "n_analyzed": coverage.n_analyzed,
            "by_dim": coverage.by_dim,
        },
        "target_rows": [dataclasses.asdict(r) for r in coverage.target_rows],
        "missing_targets": [dataclasses.asdict(r) for r in coverage.missing],
        "extra_local_logical_keys": coverage.extra_local_keys,
    }


def _build_funnel_sankey_rows(coverage: CoverageReport) -> list[dict[str, str]]:
    """One row per target; flows through stage-named labels split by model."""
    rows: list[dict[str, str]] = []
    for r in coverage.target_rows:
        scope_label = "scope (target)"
        # Determine the deepest stage this row reaches:
        if r.has_analyzed_local:
            outcome = "analyzed"
        elif r.has_completed_local:
            outcome = "completed (not analyzed)"
        elif r.matched_logical:
            outcome = "reproduced (no run_path)"
        else:
            outcome = "missing (no local repro)"
        rows.append({
            "scope": scope_label,
            "model": r.model or "unknown",
            "benchmark": r.benchmark or "unknown",
            "suite_version": r.suite_version or "unknown",
            "outcome": outcome,
        })
    return rows


def _missing_csv_rows(coverage: CoverageReport) -> list[dict[str, str]]:
    return [
        {
            "model": r.model,
            "benchmark": r.benchmark,
            "suite_version": r.suite_version,
            "public_track": r.public_track,
            "logical_run_key": r.logical_run_key,
            "run_name": r.run_name,
            "target_run_path": r.target_run_path or "",
        }
        for r in coverage.missing
    ]


def _by_dim_csv_rows(coverage: CoverageReport, dim: str) -> list[dict[str, Any]]:
    return [{"dim": dim, **entry} for entry in coverage.by_dim.get(dim, [])]


def _write_text(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines and not lines[-1].endswith("\n") else ""))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fieldnames = sorted({k for r in rows for k in r.keys()})
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_coverage_artifacts(
    coverage: CoverageReport,
    *,
    out_dpath: Path,
) -> dict[str, Path]:
    """Emit the Stage-B coverage funnel artifacts under ``out_dpath``.

    Layout (all latest-aliased)::

        out_dpath/
          coverage_funnel_summary.latest.txt
          coverage_funnel.latest.json
          missing_targets.latest.csv
          coverage_by_<dim>.latest.csv      (one per breakdown_dim)
          sankey_b_scope_to_analyzed.latest.{html,jpg,txt}   (when plotly+chrome available)
    """
    out_dpath = Path(out_dpath).expanduser().resolve()
    out_dpath.mkdir(parents=True, exist_ok=True)
    stamp, history_dpath = stamped_history_dir(out_dpath)

    # Pre-clean any stale latest aliases we own so an empty re-run doesn't
    # leave dangling files from a richer prior run.
    for alias_name in [
        "coverage_funnel_summary.latest.txt",
        "coverage_funnel.latest.json",
        "missing_targets.latest.csv",
        "missing_targets.latest.txt",
        "sankey_b_scope_to_analyzed.latest.html",
        "sankey_b_scope_to_analyzed.latest.jpg",
        "sankey_b_scope_to_analyzed.latest.txt",
        "sankey_b_scope_to_analyzed.latest.json",
    ]:
        safe_unlink(out_dpath / alias_name)
    for dim in coverage.by_dim:
        safe_unlink(out_dpath / f"coverage_by_{dim}.latest.csv")

    summary_lines = _format_summary(coverage)
    summary_fpath = history_dpath / f"coverage_funnel_summary_{stamp}.txt"
    _write_text(summary_fpath, summary_lines)
    write_latest_alias(summary_fpath, out_dpath, "coverage_funnel_summary.latest.txt")

    json_fpath = history_dpath / f"coverage_funnel_{stamp}.json"
    _write_json(json_fpath, _coverage_payload(coverage))
    write_latest_alias(json_fpath, out_dpath, "coverage_funnel.latest.json")

    missing_csv_fpath = history_dpath / f"missing_targets_{stamp}.csv"
    _write_csv(missing_csv_fpath, _missing_csv_rows(coverage))
    write_latest_alias(missing_csv_fpath, out_dpath, "missing_targets.latest.csv")

    missing_txt_lines = [f"Missing targets ({len(coverage.missing)}):"] + [
        f"  - [{r.model}/{r.benchmark}/{r.suite_version}] {r.run_name}"
        for r in coverage.missing
    ]
    missing_txt_fpath = history_dpath / f"missing_targets_{stamp}.txt"
    _write_text(missing_txt_fpath, missing_txt_lines)
    write_latest_alias(missing_txt_fpath, out_dpath, "missing_targets.latest.txt")

    by_dim_paths: dict[str, Path] = {}
    for dim in coverage.by_dim:
        csv_fpath = history_dpath / f"coverage_by_{dim}_{stamp}.csv"
        _write_csv(csv_fpath, _by_dim_csv_rows(coverage, dim))
        write_latest_alias(csv_fpath, out_dpath, f"coverage_by_{dim}.latest.csv")
        by_dim_paths[dim] = csv_fpath

    # Sankey: rows split by model -> outcome. Same shape as build_reports_summary's
    # operational sankeys so a future Stage-A sankey can sit alongside.
    funnel_rows = _build_funnel_sankey_rows(coverage)
    root = sankey_builder.Root(label=f"Coverage Funnel — {coverage.name} n={len(funnel_rows)}")
    node = root
    for key, name in [("scope", "scope (target)"), ("model", "model"), ("outcome", "outcome")]:
        # always include all stages even when degenerate so the structure is
        # legible; if a stage has only one value it's still a useful waypoint.
        node = node.group(by=key, name=name)
    sankey_paths = emit_sankey_artifacts(
        rows=funnel_rows,
        report_dpath=out_dpath,
        stamp=stamp,
        kind="b_scope_to_analyzed",
        title=f"Stage B Coverage — {coverage.name}",
        stage_defs={},
        stage_order=[("scope", "scope (target)"), ("model", "model"), ("outcome", "outcome")],
        root=root,
        explicit_stage_names=["scope (target)", "model", "outcome"],
    )

    paths: dict[str, Path] = {
        "summary_txt": out_dpath / "coverage_funnel_summary.latest.txt",
        "json": out_dpath / "coverage_funnel.latest.json",
        "missing_csv": out_dpath / "missing_targets.latest.csv",
        "missing_txt": out_dpath / "missing_targets.latest.txt",
    }
    for dim in coverage.by_dim:
        paths[f"by_{dim}_csv"] = out_dpath / f"coverage_by_{dim}.latest.csv"
    return paths
