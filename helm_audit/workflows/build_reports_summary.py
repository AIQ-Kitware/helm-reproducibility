from __future__ import annotations

import argparse
import csv
import datetime as datetime_mod
import json
import os
import resource
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import kwutil

from helm_audit.infra.api import audit_root, default_report_root
from helm_audit.infra.fs_publish import stamped_history_dir, symlink_to, write_latest_alias
from helm_audit.utils.sankey import emit_sankey_artifacts


DEFAULT_BREAKDOWN_DIMS = [
    "experiment_name",
    "model",
    "benchmark",
    "suite",
    "machine_host",
]


def latest_index_csv(index_dpath: Path) -> Path:
    cands = sorted(index_dpath.glob("audit_results_index_*.csv"), reverse=True)
    if not cands:
        raise FileNotFoundError(f"No index csv files found in {index_dpath}")
    return cands[0]


def load_rows(index_fpath: Path) -> list[dict[str, Any]]:
    with index_fpath.open(newline="") as file:
        return [{k: ("" if v is None else v) for k, v in row.items()} for row in csv.DictReader(file)]


def slugify(text: str) -> str:
    return (
        text.replace("/", "-")
        .replace(":", "-")
        .replace(",", "-")
        .replace("=", "-")
        .replace("@", "-")
        .replace(" ", "-")
    )


def _load_json(fpath: Path) -> dict[str, Any]:
    return json.loads(fpath.read_text())


def _write_json(payload: Any, fpath: Path) -> None:
    fpath.write_text(json.dumps(kwutil.Json.ensure_serializable(payload), indent=2))


def _write_text(lines: list[str], fpath: Path) -> None:
    fpath.write_text("\n".join(lines).rstrip() + "\n")


def _find_pair(report: dict[str, Any], label: str) -> dict[str, Any]:
    for pair in report.get("pairs", []):
        if pair.get("label") == label:
            return pair
    return {}


def _find_curve_value(rows: list[dict[str, Any]], abs_tol: float) -> float | None:
    for row in rows or []:
        try:
            if float(row.get("abs_tol")) == float(abs_tol):
                return float(row.get("agree_ratio"))
        except Exception:
            pass
    return None


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_truthy_text(value: Any) -> bool:
    return _normalize_text(value) in {"true", "1", "yes"}


def _bucket_agreement(agree_ratio: float | None) -> str:
    if agree_ratio is None:
        return "not_analyzed"
    if agree_ratio >= 0.999999:
        return "exact_or_near_exact"
    if agree_ratio >= 0.95:
        return "high_agreement_0.95+"
    if agree_ratio >= 0.80:
        return "moderate_agreement_0.80+"
    if agree_ratio > 0.0:
        return "low_agreement_0.00+"
    return "zero_agreement"


def _read_log_tail(job_dpath: Path, max_chars: int = 40000) -> str:
    log_fpath = job_dpath / "helm-run.log"
    if not log_fpath.exists():
        return ""
    try:
        text = log_fpath.read_text(errors="ignore")
    except Exception:
        return ""
    return text[-max_chars:]


def _classify_failure(job_dpath: Path, row: dict[str, Any]) -> dict[str, Any]:
    log_tail = _read_log_tail(job_dpath)
    text = _normalize_text(log_tail)
    status = _normalize_text(row.get("status"))

    checks: list[tuple[str, str, list[str]]] = [
        (
            "missing_openai_annotation_credentials",
            "run depends on OpenAI-backed annotation but no API key was configured",
            ["openai_api_key", "annotationexecutorerror", "api_key client option must be set"],
        ),
        (
            "missing_math_dataset",
            "required math dataset was not available in the environment",
            ["hendrycks/competition_math", "couldn't find 'hendrycks/competition_math'"],
        ),
        (
            "missing_dataset_or_cached_artifact",
            "required dataset or cached artifact was not available",
            ["filenotfounderror", "couldn't find", "no such file or directory"],
        ),
        (
            "gated_dataset_access",
            "dataset exists but requires gated access credentials or approval",
            ["gated dataset on the hub", "ask for access", "datasetnotfounderror: dataset"],
        ),
        (
            "remote_dataset_download_failure",
            "dataset download failed from a remote source",
            ["failed with exit code 8: wget", "wget https://", "curl: ", "temporary failure in name resolution"],
        ),
        (
            "gpu_memory_or_cuda_failure",
            "job hit a CUDA or GPU-memory related failure",
            ["cuda out of memory", "outofmemoryerror", "cublas", "cuda error"],
        ),
        (
            "process_killed_or_resource_exhausted",
            "process looks to have been killed by the host or scheduler",
            ["killed", "exit code 137", "sigkill"],
        ),
        (
            "network_or_remote_service_failure",
            "remote service or network interaction failed",
            ["connectionerror", "readtimeout", "maxretryerror", "429", "503 service unavailable"],
        ),
        (
            "filesystem_permission_failure",
            "filesystem permissions blocked the run",
            ["permission denied"],
        ),
        (
            "interrupted_run",
            "run was interrupted before completion",
            ["keyboardinterrupt", "cancellederror", "interrupted"],
        ),
    ]

    for label, summary, patterns in checks:
        matched = [pat for pat in patterns if pat in text]
        if matched:
            return {
                "failure_reason": label,
                "failure_summary": summary,
                "failure_confidence": "heuristic_pattern_match",
                "matched_patterns": matched,
                "log_excerpt": log_tail[-2000:] if log_tail else None,
            }

    if status in {"running", "queued"}:
        return {
            "failure_reason": "not_finished_yet",
            "failure_summary": "job appears to be queued or still running",
            "failure_confidence": "status_only",
            "matched_patterns": [],
            "log_excerpt": log_tail[-2000:] if log_tail else None,
        }

    if not log_tail:
        return {
            "failure_reason": "missing_runtime_log",
            "failure_summary": "no runtime log was found for this job",
            "failure_confidence": "missing_evidence",
            "matched_patterns": [],
            "log_excerpt": None,
        }

    if "traceback" not in text and status in {"", "unknown", "computed", "reused"}:
        return {
            "failure_reason": "truncated_or_incomplete_runtime",
            "failure_summary": "job lacks complete run artifacts and the runtime log ends without a clear terminal exception",
            "failure_confidence": "weak_inference",
            "matched_patterns": [],
            "log_excerpt": log_tail[-2000:] if log_tail else None,
        }

    return {
        "failure_reason": "unknown_failure",
        "failure_summary": "no current rule explains this failure; manual drill-down recommended",
        "failure_confidence": "unknown",
        "matched_patterns": [],
        "log_excerpt": log_tail[-2000:] if log_tail else None,
    }


def _configure_plotly_chrome() -> None:
    chrome_candidates = [
        audit_root() / ".cache/plotly-chrome/chrome-linux64/chrome",
        Path.home() / ".plotly/chrome/chrome-linux64/chrome",
    ]
    for cand in chrome_candidates:
        if cand.exists():
            os.environ.setdefault("BROWSER_PATH", str(cand))
            os.environ.setdefault("PLOTLY_CHROME_PATH", str(cand))
            break
    os.environ.setdefault("HELM_AUDIT_SKIP_STATIC_IMAGES", "1")
    os.environ.setdefault("HELM_AUDIT_SKIP_PLOTLY", "1")


def _raise_fd_limit(target: int = 8192) -> None:
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        desired = min(max(soft, target), hard)
        if desired > soft:
            resource.setrlimit(resource.RLIMIT_NOFILE, (desired, hard))
    except Exception:
        pass


def _fd_count() -> int | None:
    try:
        return len(os.listdir("/proc/self/fd"))
    except Exception:
        return None


def _load_all_repro_rows() -> list[dict[str, Any]]:
    report_jsons = sorted(
        default_report_root().glob("experiment-analysis-*/core-reports/*/core_metric_report.latest.json")
    )
    deduped: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    for report_json in report_jsons:
        try:
            report = _load_json(report_json)
        except Exception:
            continue
        selection_fpath = report_json.parent / "report_selection.latest.json"
        selection = _load_json(selection_fpath) if selection_fpath.exists() else {}
        experiment_name = selection.get("experiment_name")
        run_entry = selection.get("run_entry")
        if not experiment_name or not run_entry:
            continue
        official = _find_pair(report, "official_vs_kwdagger") or {}
        repeat = _find_pair(report, "kwdagger_repeat") or {}
        official_diag = official.get("diagnosis", {}) or {}
        repeat_diag = repeat.get("diagnosis", {}) or {}
        agree_0 = _find_curve_value(
            ((official.get("instance_level") or {}).get("agreement_vs_abs_tol") or []),
            0.0,
        )
        row = {
            "experiment_name": experiment_name,
            "run_entry": run_entry,
            "run_spec_name": report.get("run_spec_name"),
            "report_dir": str(report_json.parent),
            "report_json": str(report_json),
            "repeat_diagnosis": repeat_diag.get("label"),
            "repeat_primary_reasons": repeat_diag.get("primary_reason_names") or [],
            "official_diagnosis": official_diag.get("label"),
            "official_primary_reasons": official_diag.get("primary_reason_names") or [],
            "official_instance_agree_0": agree_0,
            "official_instance_agree_bucket": _bucket_agreement(agree_0),
            "official_instance_agree_01": _find_curve_value(
                ((official.get("instance_level") or {}).get("agreement_vs_abs_tol") or []),
                0.1,
            ),
            "official_runlevel_abs_max": ((((official.get("run_level") or {}).get("overall_quantiles") or {}).get("abs_delta") or {}).get("max")),
            "official_runlevel_abs_p90": ((((official.get("run_level") or {}).get("overall_quantiles") or {}).get("abs_delta") or {}).get("p90")),
        }
        deduped[(experiment_name, run_entry)] = row
    return list(deduped.values())


def _write_table_artifacts(rows: list[dict[str, Any]], stem: Path) -> dict[str, str]:
    json_fpath = stem.with_suffix(".json")
    csv_fpath = stem.with_suffix(".csv")
    txt_fpath = stem.with_suffix(".txt")
    _write_json(rows, json_fpath)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with csv_fpath.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    if not rows:
        txt_fpath.write_text("(no rows)\n")
    else:
        lines = [", ".join(fieldnames)]
        for row in rows[:200]:
            lines.append(", ".join(str(row.get(key, "")) for key in fieldnames))
        if len(rows) > 200:
            lines.append(f"... ({len(rows) - 200} more rows)")
        txt_fpath.write_text("\n".join(lines) + "\n")
    return {"json": str(json_fpath), "csv": str(csv_fpath), "txt": str(txt_fpath)}


def _write_plotly_bar(
    *,
    rows: list[dict[str, Any]],
    x: str,
    y: str,
    color: str,
    title: str,
    stem: Path,
) -> dict[str, str | None]:
    json_fpath = stem.with_suffix(".json")
    html_fpath = stem.with_suffix(".html")
    jpg_fpath = stem.with_suffix(".jpg")
    png_fpath = stem.with_suffix(".png")
    _write_json(rows, json_fpath)
    html_out = None
    jpg_out = None
    png_out = None
    plotly_error = None
    if os.environ.get("HELM_AUDIT_SKIP_PLOTLY", "") not in {"1", "true", "yes"}:
        try:
            _configure_plotly_chrome()
            import plotly.express as px

            fig = px.bar(rows, x=x, y=y, color=color, title=title, barmode="stack")
            fig.update_layout(xaxis_title=x.replace("_", " "), yaxis_title=y.replace("_", " "))
            fig.write_html(str(html_fpath), include_plotlyjs="cdn")
            html_out = str(html_fpath)
            if os.environ.get("HELM_AUDIT_SKIP_STATIC_IMAGES", "") not in {"1", "true", "yes"}:
                fig.write_image(str(jpg_fpath), scale=2.0)
                jpg_out = str(jpg_fpath)
        except Exception as ex:
            plotly_error = f"unable to write bar HTML/images: {ex!r}"
    else:
        plotly_error = "skipped plotly bar rendering by configuration"
    try:
        import matplotlib.pyplot as plt

        if rows:
            x_values = sorted({str(row.get(x, "")) for row in rows})
            color_values = sorted({str(row.get(color, "")) for row in rows})
            counts = {(str(row.get(x, "")), str(row.get(color, ""))): float(row.get(y, 0) or 0) for row in rows}
            bottoms = [0.0 for _ in x_values]
            fig, ax = plt.subplots(figsize=(12, 6))
            for color_value in color_values:
                vals = [counts.get((xv, color_value), 0.0) for xv in x_values]
                ax.bar(x_values, vals, bottom=bottoms, label=color_value)
                bottoms = [a + b for a, b in zip(bottoms, vals)]
            ax.set_title(title)
            ax.set_xlabel(x.replace("_", " "))
            ax.set_ylabel(y.replace("_", " "))
            ax.tick_params(axis="x", rotation=45)
            ax.legend(fontsize=8)
            fig.tight_layout()
            fig.savefig(png_fpath, dpi=200)
            png_out = str(png_fpath)
            if jpg_out is None:
                fig.savefig(jpg_fpath, dpi=200)
                jpg_out = str(jpg_fpath)
            plt.close(fig)
    except Exception:
        pass
    return {
        "json": str(json_fpath),
        "html": html_out,
        "jpg": jpg_out,
        "png": png_out,
        "plotly_error": plotly_error,
    }


def _scope_summary_root(summary_root: Path, scope_slug: str) -> Path:
    return summary_root / scope_slug


def _scope_label(scope_kind: str, scope_value: str | None) -> str:
    if scope_kind == "all_results":
        return "all_results"
    return f"{scope_kind}={scope_value}"


def _scope_slug(scope_kind: str, scope_value: str | None) -> str:
    if scope_kind == "all_results":
        return "all-results"
    return f"{scope_kind}-{slugify(str(scope_value))}"


def _build_breakdown_rows(
    enriched_rows: list[dict[str, Any]],
    *,
    group_key: str,
    repro_keyed: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in enriched_rows:
        group_value = str(row.get(group_key) or "unknown")
        if row.get("completed_with_run_artifacts"):
            repro = repro_keyed.get((str(row.get("experiment_name")), str(row.get("run_entry"))))
            status = "completed_not_yet_analyzed"
            if repro is not None:
                status = f"analyzed::{repro['official_instance_agree_bucket']}"
        else:
            status = f"failed::{row.get('failure_reason') or 'unknown_failure'}"
        counts[(group_value, status)] += 1
    return [
        {"group_value": group_value, "status_bucket": status, "count": count}
        for (group_value, status), count in sorted(counts.items())
    ]


def _summarize_by_dimension(
    enriched_rows: list[dict[str, Any]],
    *,
    dimension: str,
    repro_keyed: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    by_value: dict[str, dict[str, Any]] = {}
    for row in enriched_rows:
        value = str(row.get(dimension) or "unknown")
        info = by_value.setdefault(
            value,
            {
                dimension: value,
                "total_jobs": 0,
                "completed_jobs": 0,
                "analyzed_jobs": 0,
                "failed_jobs": 0,
                "failure_reasons": Counter(),
            },
        )
        info["total_jobs"] += 1
        if row.get("completed_with_run_artifacts"):
            info["completed_jobs"] += 1
            key = (str(row.get("experiment_name")), str(row.get("run_entry")))
            if key in repro_keyed:
                info["analyzed_jobs"] += 1
        else:
            info["failed_jobs"] += 1
            info["failure_reasons"][row.get("failure_reason") or "unknown_failure"] += 1
    rows = []
    for value, info in sorted(by_value.items()):
        rows.append(
            {
                dimension: value,
                "total_jobs": info["total_jobs"],
                "completed_jobs": info["completed_jobs"],
                "analyzed_jobs": info["analyzed_jobs"],
                "failed_jobs": info["failed_jobs"],
                "completion_rate": (info["completed_jobs"] / info["total_jobs"]) if info["total_jobs"] else None,
                "top_failure_reason": info["failure_reasons"].most_common(1)[0][0] if info["failure_reasons"] else None,
            }
        )
    return rows


def _build_high_level_readme(
    *,
    scope_title: str,
    generated_utc: str,
    n_total: int,
    n_completed: int,
    n_analyzed: int,
    n_failed: int,
    top_failure_rows: list[dict[str, Any]],
    top_repro_rows: list[dict[str, Any]],
    breakdown_dims: list[str],
) -> list[str]:
    lines = [
        "Executive Summary",
        "",
        f"generated_utc: {generated_utc}",
        f"scope: {scope_title}",
        f"total_jobs: {n_total}",
        f"completed_with_run_artifacts: {n_completed}",
        f"completed_and_analyzed: {n_analyzed}",
        f"failed_or_incomplete: {n_failed}",
        "",
        "key_takeaways:",
        f"  - {n_completed}/{n_total} jobs produced runnable HELM artifacts in this scope.",
        f"  - {n_analyzed} completed jobs in this scope already have reproducibility reports.",
    ]
    if top_failure_rows:
        lines.append("  - dominant failure reasons currently appear to be:")
        for row in top_failure_rows[:5]:
            lines.append(f"    * {row['failure_reason']}: {row['count']}")
    if top_repro_rows:
        lines.append("  - analyzed reproducibility buckets currently are:")
        for row in top_repro_rows[:5]:
            lines.append(f"    * {row['official_instance_agree_bucket']}: {row['count']}")
    lines.extend(
        [
            "",
            "start_here:",
            "  - open sankey_operational.latest.html for the full pipeline from group to success/failure bucket",
            "  - open sankey_reproducibility.latest.html for the analyzed subset and agreement thresholds",
            "  - read failure_reasons.latest.txt to see why incomplete jobs likely failed",
            "  - follow next_level/ for tables and breakdown folders",
            "",
            "default_breakdowns:",
        ]
    )
    for dim in breakdown_dims:
        lines.append(f"  - {dim}")
    return lines


def _write_scope_level_aliases(level_001: Path, level_002: Path, summary_root: Path) -> None:
    write_latest_alias(level_001 / "README.latest.txt", summary_root, "README.latest.txt")
    write_latest_alias(level_001, summary_root, "level_001.latest")
    write_latest_alias(level_002, summary_root, "level_002.latest")
    for src_name in [
        "sankey_operational.latest.html",
        "sankey_operational.latest.jpg",
        "sankey_operational.latest.txt",
        "sankey_reproducibility.latest.html",
        "sankey_reproducibility.latest.jpg",
        "sankey_reproducibility.latest.txt",
        "benchmark_status.latest.html",
        "benchmark_status.latest.jpg",
        "reproducibility_buckets.latest.html",
        "reproducibility_buckets.latest.jpg",
        "failure_reasons.latest.txt",
        "failure_runs.latest.csv",
    ]:
        src = level_001 / src_name
        if src.exists() or src.is_symlink():
            write_latest_alias(src, summary_root, src_name)
    for src_name in [
        "benchmark_summary.latest.csv",
        "run_inventory.latest.csv",
        "reproducibility_rows.latest.csv",
    ]:
        src = level_002 / src_name
        if src.exists() or src.is_symlink():
            write_latest_alias(src, summary_root, src_name)


def _render_breakdown_scopes(
    *,
    enriched_rows: list[dict[str, Any]],
    all_repro_rows: list[dict[str, Any]],
    breakdown_dims: list[str],
    level_002: Path,
    max_items_per_breakdown: int,
) -> None:
    breakdowns_root = level_002 / "breakdowns"
    breakdowns_root.mkdir(parents=True, exist_ok=True)
    repro_keyed = {
        (str(row.get("experiment_name")), str(row.get("run_entry"))): row
        for row in all_repro_rows
        if row.get("experiment_name") and row.get("run_entry")
    }
    manifest_rows = []
    for dim in breakdown_dims:
        value_counts = Counter(str(row.get(dim) or "unknown") for row in enriched_rows)
        dim_root = breakdowns_root / f"by_{dim}"
        dim_root.mkdir(parents=True, exist_ok=True)
        top_values = [value for value, _ in value_counts.most_common(max_items_per_breakdown)]
        summary_rows = _summarize_by_dimension(enriched_rows, dimension=dim, repro_keyed=repro_keyed)
        table_artifacts = _write_table_artifacts(summary_rows, dim_root / f"index_{slugify(dim)}")
        for kind in ["json", "csv", "txt"]:
            write_latest_alias(Path(table_artifacts[kind]), dim_root, f"index.latest.{kind}")
        for value in top_values:
            child_rows = [row for row in enriched_rows if str(row.get(dim) or "unknown") == value]
            child_repro = [
                row
                for row in all_repro_rows
                if (str(row.get("experiment_name")), str(row.get("run_entry"))) in {
                    (str(item.get("experiment_name")), str(item.get("run_entry"))) for item in child_rows
                }
            ]
            child_root = dim_root / slugify(value)
            _render_scope_summary(
                scope_kind=dim,
                scope_value=value,
                scope_rows=child_rows,
                repro_rows=child_repro,
                summary_root=child_root,
                breakdown_dims=[],
                max_items_per_breakdown=max_items_per_breakdown,
                include_visuals=False,
            )
            manifest_rows.append(
                {
                    "breakdown": dim,
                    "value": value,
                    "n_jobs": len(child_rows),
                    "summary_root": str(child_root),
                }
            )
    manifest_fpath = breakdowns_root / "manifest.json"
    _write_json(manifest_rows, manifest_fpath)
    write_latest_alias(manifest_fpath, breakdowns_root, "manifest.latest.json")


def _render_scope_summary(
    *,
    scope_kind: str,
    scope_value: str | None,
    scope_rows: list[dict[str, Any]],
    repro_rows: list[dict[str, Any]],
    summary_root: Path,
    breakdown_dims: list[str],
    max_items_per_breakdown: int,
    include_visuals: bool = True,
) -> None:
    if not scope_rows:
        return

    generated_utc, history_dpath = stamped_history_dir(summary_root)
    version_dpath = history_dpath / generated_utc
    level_001 = version_dpath / "level_001"
    level_002 = version_dpath / "level_002"
    level_001.mkdir(parents=True, exist_ok=True)
    level_002.mkdir(parents=True, exist_ok=True)

    repro_keyed = {
        (str(row.get("experiment_name")), str(row.get("run_entry"))): row
        for row in repro_rows
        if row.get("experiment_name") and row.get("run_entry")
    }

    enriched_rows: list[dict[str, Any]] = []
    failed_rows: list[dict[str, Any]] = []
    for row in scope_rows:
        enriched = dict(row)
        completed = _is_truthy_text(row.get("has_run_spec"))
        enriched["completed_with_run_artifacts"] = completed
        enriched["lifecycle_stage"] = "completed_with_run_artifacts" if completed else "failed_or_incomplete"
        key = (str(row.get("experiment_name")), str(row.get("run_entry")))
        repro = repro_keyed.get(key)
        if repro is not None:
            enriched.update(
                {
                    "repro_report_dir": repro.get("report_dir"),
                    "official_instance_agree_0": repro.get("official_instance_agree_0"),
                    "official_instance_agree_bucket": repro.get("official_instance_agree_bucket"),
                    "official_diagnosis": repro.get("official_diagnosis"),
                    "repeat_diagnosis": repro.get("repeat_diagnosis"),
                }
            )
        elif completed:
            enriched["official_instance_agree_bucket"] = "completed_not_yet_analyzed"
        if not completed:
            failure = _classify_failure(Path(str(row.get("job_dpath"))).expanduser(), row)
            enriched.update(failure)
            failed_rows.append(enriched)
        enriched_rows.append(enriched)

    n_total = len(enriched_rows)
    n_completed = sum(1 for row in enriched_rows if row.get("completed_with_run_artifacts"))
    n_failed = n_total - n_completed
    n_analyzed = len(repro_rows)

    failure_counts = Counter(row.get("failure_reason") or "unknown_failure" for row in failed_rows)
    failure_reason_rows = [
        {"failure_reason": reason, "count": count, "share_of_failed": (count / n_failed) if n_failed else None}
        for reason, count in failure_counts.most_common()
    ]
    repro_bucket_counts = Counter(row.get("official_instance_agree_bucket") or "not_analyzed" for row in repro_rows)
    repro_bucket_rows = [
        {
            "official_instance_agree_bucket": bucket,
            "count": count,
            "share_of_analyzed": (count / n_analyzed) if n_analyzed else None,
        }
        for bucket, count in repro_bucket_counts.most_common()
    ]

    benchmark_status_rows = _build_breakdown_rows(enriched_rows, group_key="benchmark", repro_keyed=repro_keyed)
    benchmark_summary = _summarize_by_dimension(enriched_rows, dimension="benchmark", repro_keyed=repro_keyed)
    run_inventory = enriched_rows
    repro_inventory = repro_rows

    operational_sankey_rows = []
    for row in enriched_rows:
        if row.get("completed_with_run_artifacts"):
            outcome = str(row.get("official_instance_agree_bucket") or "completed_not_yet_analyzed")
        else:
            outcome = str(row.get("failure_reason") or "unknown_failure")
        operational_sankey_rows.append(
            {
                "group": str(row.get("benchmark") or "unknown"),
                "lifecycle": str(row.get("lifecycle_stage") or "unknown"),
                "outcome": outcome,
            }
        )

    repro_sankey_rows = []
    for row in repro_rows:
        parent = next(
            (
                item for item in enriched_rows
                if str(item.get("experiment_name")) == str(row.get("experiment_name"))
                and str(item.get("run_entry")) == str(row.get("run_entry"))
            ),
            None,
        )
        repro_sankey_rows.append(
            {
                "group": str((parent or {}).get("benchmark") or "unknown"),
                "repeatability": str(row.get("repeat_diagnosis") or "unknown"),
                "agreement": str(row.get("official_instance_agree_bucket") or "not_analyzed"),
                "diagnosis": str(row.get("official_diagnosis") or "unknown"),
            }
        )

    scope_title = _scope_label(scope_kind, scope_value)
    if include_visuals:
        operational_art = emit_sankey_artifacts(
            rows=operational_sankey_rows,
            report_dpath=level_001,
            stamp=generated_utc,
            kind="operational",
            title=f"Executive Operational Summary: {scope_title}",
            stage_defs={
                "group": ["benchmark family or suite"],
                "lifecycle": ["whether the run produced runnable artifacts"],
                "outcome": ["failure reason or reproducibility threshold bucket"],
            },
            stage_order=[("group", "group"), ("lifecycle", "lifecycle"), ("outcome", "outcome")],
        )
        repro_art = emit_sankey_artifacts(
            rows=repro_sankey_rows,
            report_dpath=level_001,
            stamp=generated_utc,
            kind="reproducibility",
            title=f"Executive Reproducibility Summary: {scope_title}",
            stage_defs={
                "group": ["benchmark family or suite"],
                "repeatability": ["local repeatability diagnosis"],
                "agreement": ["official-vs-local strict agreement bucket at abs_tol=0.0"],
                "diagnosis": ["top-level diagnosis from official-vs-local comparison"],
            },
            stage_order=[
                ("group", "group"),
                ("repeatability", "repeatability"),
                ("agreement", "agreement"),
                ("diagnosis", "diagnosis"),
            ],
        )
    else:
        operational_art = {"json": None, "txt": None, "key_txt": None, "html": None, "jpg": None, "plotly_error": None}
        repro_art = {"json": None, "txt": None, "key_txt": None, "html": None, "jpg": None, "plotly_error": None}

    failure_table = _write_table_artifacts(failed_rows, level_001 / f"failure_runs_{generated_utc}")
    failure_reason_table = _write_table_artifacts(failure_reason_rows, level_001 / f"failure_reasons_{generated_utc}")
    benchmark_table = _write_table_artifacts(benchmark_summary, level_002 / f"benchmark_summary_{generated_utc}")
    run_inventory_table = _write_table_artifacts(run_inventory, level_002 / f"run_inventory_{generated_utc}")
    repro_table = _write_table_artifacts(repro_inventory, level_002 / f"reproducibility_rows_{generated_utc}")

    if include_visuals:
        benchmark_plot = _write_plotly_bar(
            rows=benchmark_status_rows,
            x="group_value",
            y="count",
            color="status_bucket",
            title=f"Benchmark Coverage and Analysis Status: {scope_title}",
            stem=level_001 / f"benchmark_status_{generated_utc}",
        )
        repro_bucket_plot = _write_plotly_bar(
            rows=repro_bucket_rows,
            x="official_instance_agree_bucket",
            y="count",
            color="official_instance_agree_bucket",
            title=f"Official vs Local Agreement Buckets: {scope_title}",
            stem=level_001 / f"reproducibility_buckets_{generated_utc}",
        )
    else:
        benchmark_plot = {"json": None, "html": None, "jpg": None, "png": None, "plotly_error": None}
        repro_bucket_plot = {"json": None, "html": None, "jpg": None, "png": None, "plotly_error": None}

    level_001_readme = _build_high_level_readme(
        scope_title=scope_title,
        generated_utc=generated_utc,
        n_total=n_total,
        n_completed=n_completed,
        n_analyzed=n_analyzed,
        n_failed=n_failed,
        top_failure_rows=failure_reason_rows,
        top_repro_rows=repro_bucket_rows,
        breakdown_dims=breakdown_dims,
    )
    _write_text(level_001_readme, level_001 / f"README_{generated_utc}.txt")

    level_002_lines = [
        "Drilldown Summary",
        "",
        f"generated_utc: {generated_utc}",
        f"scope: {scope_title}",
        "",
        "contents:",
        "  - benchmark_summary.latest.csv: benchmark-level counts and top failure reason",
        "  - run_inventory.latest.csv: one row per scheduled job with completion, failure, and repro fields",
        "  - reproducibility_rows.latest.csv: analyzed per-run reproducibility cases in this scope",
    ]
    if breakdown_dims:
        level_002_lines.append("  - breakdowns/: reusable summaries for additional cuts of the same data")
    _write_text(level_002_lines, level_002 / f"README_{generated_utc}.txt")

    latest_pairs = [
        (level_001 / f"README_{generated_utc}.txt", level_001, "README.latest.txt"),
        (level_002 / f"README_{generated_utc}.txt", level_002, "README.latest.txt"),
        (Path(failure_table["json"]), level_001, "failure_runs.latest.json"),
        (Path(failure_table["csv"]), level_001, "failure_runs.latest.csv"),
        (Path(failure_table["txt"]), level_001, "failure_runs.latest.txt"),
        (Path(failure_reason_table["json"]), level_001, "failure_reasons.latest.json"),
        (Path(failure_reason_table["csv"]), level_001, "failure_reasons.latest.csv"),
        (Path(failure_reason_table["txt"]), level_001, "failure_reasons.latest.txt"),
        (Path(benchmark_table["json"]), level_002, "benchmark_summary.latest.json"),
        (Path(benchmark_table["csv"]), level_002, "benchmark_summary.latest.csv"),
        (Path(benchmark_table["txt"]), level_002, "benchmark_summary.latest.txt"),
        (Path(run_inventory_table["json"]), level_002, "run_inventory.latest.json"),
        (Path(run_inventory_table["csv"]), level_002, "run_inventory.latest.csv"),
        (Path(run_inventory_table["txt"]), level_002, "run_inventory.latest.txt"),
        (Path(repro_table["json"]), level_002, "reproducibility_rows.latest.json"),
        (Path(repro_table["csv"]), level_002, "reproducibility_rows.latest.csv"),
        (Path(repro_table["txt"]), level_002, "reproducibility_rows.latest.txt"),
    ]
    for src, root, name in latest_pairs:
        write_latest_alias(src, root, name)

    if include_visuals:
        for base_name, artifact in [("benchmark_status", benchmark_plot), ("reproducibility_buckets", repro_bucket_plot)]:
            write_latest_alias(Path(artifact["json"]), level_001, f"{base_name}.latest.json")
            if artifact.get("html"):
                write_latest_alias(Path(str(artifact["html"])), level_001, f"{base_name}.latest.html")
            if artifact.get("png"):
                write_latest_alias(Path(str(artifact["png"])), level_001, f"{base_name}.latest.png")
            if artifact.get("jpg"):
                write_latest_alias(Path(str(artifact["jpg"])), level_001, f"{base_name}.latest.jpg")

    manifest = {
        "generated_utc": generated_utc,
        "scope_kind": scope_kind,
        "scope_value": scope_value,
        "scope_title": scope_title,
        "summary_root": str(summary_root),
        "version_dpath": str(version_dpath),
        "level_001": str(level_001),
        "level_002": str(level_002),
        "n_total": n_total,
        "n_completed": n_completed,
        "n_failed": n_failed,
        "n_analyzed": n_analyzed,
        "breakdown_dims": breakdown_dims,
        "operational_sankey": operational_art,
        "reproducibility_sankey": repro_art,
        "benchmark_plot": benchmark_plot,
        "repro_bucket_plot": repro_bucket_plot,
    }
    manifest_fpath = level_001 / f"summary_manifest_{generated_utc}.json"
    _write_json(manifest, manifest_fpath)
    write_latest_alias(manifest_fpath, level_001, "summary_manifest.latest.json")

    symlink_to(level_002, level_001 / "next_level")
    symlink_to(level_001, level_002 / "up_level")
    experiment_names = {str(row.get("experiment_name")) for row in enriched_rows if row.get("experiment_name")}
    if len(experiment_names) == 1:
        exp_name = next(iter(experiment_names))
        analysis_dpath = default_report_root() / f"experiment-analysis-{slugify(exp_name)}"
        if analysis_dpath.exists():
            symlink_to(analysis_dpath, level_002 / "experiment-analysis")

    if breakdown_dims:
        _render_breakdown_scopes(
            enriched_rows=enriched_rows,
            all_repro_rows=repro_rows,
            breakdown_dims=breakdown_dims,
            level_002=level_002,
            max_items_per_breakdown=max_items_per_breakdown,
        )

    _write_scope_level_aliases(level_001, level_002, summary_root)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-name", default=None)
    parser.add_argument("--index-fpath", default=None)
    parser.add_argument("--index-dpath", default=str(default_report_root() / "indexes"))
    parser.add_argument("--summary-root", default=str(audit_root() / "reports-summary"))
    parser.add_argument(
        "--breakdown-dims",
        nargs="*",
        default=DEFAULT_BREAKDOWN_DIMS,
    )
    parser.add_argument("--max-items-per-breakdown", type=int, default=12)
    args = parser.parse_args(argv)

    index_fpath = (
        Path(args.index_fpath).expanduser().resolve()
        if args.index_fpath
        else latest_index_csv(Path(args.index_dpath).expanduser().resolve())
    )
    rows = load_rows(index_fpath)
    _raise_fd_limit()
    _configure_plotly_chrome()
    all_repro_rows = _load_all_repro_rows()

    if args.experiment_name:
        scope_kind = "experiment_name"
        scope_value = args.experiment_name
        scope_rows = [row for row in rows if row.get("experiment_name") == args.experiment_name]
        if not scope_rows:
            raise SystemExit(f"No rows found for experiment_name={args.experiment_name!r}")
        repro_rows = [row for row in all_repro_rows if row.get("experiment_name") == args.experiment_name]
    else:
        scope_kind = "all_results"
        scope_value = None
        scope_rows = rows
        repro_rows = all_repro_rows

    scope_root = _scope_summary_root(
        Path(args.summary_root).expanduser().resolve(),
        _scope_slug(scope_kind, scope_value),
    )
    _render_scope_summary(
        scope_kind=scope_kind,
        scope_value=scope_value,
        scope_rows=scope_rows,
        repro_rows=repro_rows,
        summary_root=scope_root,
        breakdown_dims=list(args.breakdown_dims),
        max_items_per_breakdown=args.max_items_per_breakdown,
    )
    print(f"Wrote executive summary root: {scope_root}")


if __name__ == "__main__":
    main()
