"""
Analyze a single official/public HELM index CSV and produce executive-summary artifacts.

This tool consumes an already-built official/public index (see
`helm_audit.cli.index_historic_helm_runs --out_official_index_dpath`) and answers
questions like:
  - How many distinct tracks / suite versions are present?
  - How many run names appear in multiple versions?
  - Which run names show run_spec content drift across versions?
  - What is the logical run count under different dedup policies?

It does NOT rescan the public HELM filesystem.

Usage:
    python -m helm_audit.workflows.analyze_official_index \\
        --index_fpath /data/crfm-helm-audit-store/indexes/official_public_index.latest.csv \\
        --out_dpath   /data/crfm-helm-audit-store/analysis/official-public-index/
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import scriptconfig as scfg
from loguru import logger

from helm_audit.infra.logging import setup_cli_logging
from helm_audit.infra.paths import official_public_analysis_dpath


class AnalyzeOfficialIndexConfig(scfg.DataConfig):
    index_fpath = scfg.Value(
        None,
        help='Path to the official/public index CSV to analyze.',
        position=1,
    )
    out_dpath = scfg.Value(
        str(official_public_analysis_dpath()),
        help='Directory where analysis artifacts will be written.',
    )

    @classmethod
    def main(cls, argv=None, **kwargs):
        """
        Example:
            >>> # xdoctest: +SKIP
            >>> from helm_audit.workflows.analyze_official_index import *  # NOQA
            >>> argv = False
            >>> cls = AnalyzeOfficialIndexConfig
            >>> cls.main(argv=argv)
        """
        setup_cli_logging()
        config = cls.cli(argv=argv, data=kwargs, verbose='auto')
        if not config.index_fpath:
            raise SystemExit('--index_fpath is required')
        index_fpath = Path(config.index_fpath).expanduser().resolve()
        out_dpath = Path(config.out_dpath).expanduser().resolve()
        analyze_official_index(index_fpath=index_fpath, out_dpath=out_dpath)


def analyze_official_index(index_fpath: Path, out_dpath: Path) -> dict:
    """
    Analyze an official/public HELM index CSV and emit executive-summary artifacts.

    Args:
        index_fpath: Path to the official/public index CSV.
        out_dpath: Directory where analysis artifacts will be written.

    Returns:
        Summary dict (same content as official_index_summary.latest.json).
    """
    logger.info('Loading official public index from {}', index_fpath)
    df = pd.read_csv(index_fpath, low_memory=False)
    out_dpath.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Partition rows
    # ------------------------------------------------------------------
    df_runs = df[df['entry_kind'] == 'benchmark_run'].copy()
    n_structural_non_run = int((df['entry_kind'] == 'structural_non_run').sum())
    n_unknown_entry = int((df['entry_kind'] == 'unknown').sum())

    # ------------------------------------------------------------------
    # Top-level counts
    # ------------------------------------------------------------------
    total_rows = len(df)
    n_benchmark_runs = len(df_runs)

    tracks = sorted(df['public_track'].dropna().unique().tolist())
    suite_versions = sorted(df['suite_version'].dropna().unique().tolist())

    distinct_run_names = int(df_runs['run_name'].dropna().nunique())
    distinct_models = int(df_runs['model'].dropna().nunique())
    distinct_benchmarks = int(df_runs['benchmark_group'].dropna().nunique())
    distinct_scenario_classes = int(df_runs['scenario_class'].dropna().nunique())

    # ------------------------------------------------------------------
    # Multi-version / multi-track / hash-drift counts
    # ------------------------------------------------------------------
    run_name_version_counts = df_runs.groupby('run_name')['suite_version'].nunique()
    run_name_track_counts = df_runs.groupby('run_name')['public_track'].nunique()
    hash_df = df_runs[df_runs['run_spec_hash'].notna()]
    run_name_hash_counts = hash_df.groupby('run_name')['run_spec_hash'].nunique()

    n_run_names_multi_version = int((run_name_version_counts > 1).sum())
    n_run_names_multi_track = int((run_name_track_counts > 1).sum())
    n_run_names_with_hash_drift = int((run_name_hash_counts > 1).sum())

    # ------------------------------------------------------------------
    # Dedup views
    # ------------------------------------------------------------------
    dedup_views = {
        'raw_benchmark_run_rows': n_benchmark_runs,
        'distinct_run_name': distinct_run_names,
        'distinct_run_name_x_track': int(
            df_runs[['run_name', 'public_track']].drop_duplicates().shape[0]
        ),
        'distinct_run_spec_hash': int(df_runs['run_spec_hash'].dropna().nunique()),
    }

    # ------------------------------------------------------------------
    # Per-track breakdown
    # ------------------------------------------------------------------
    by_track = _agg_by_group(df, df_runs, 'public_track')

    # ------------------------------------------------------------------
    # Per-suite-version breakdown
    # ------------------------------------------------------------------
    by_suite = _agg_by_group(df, df_runs, 'suite_version')
    by_suite = by_suite.sort_values('suite_version')

    # ------------------------------------------------------------------
    # Per-model breakdown (benchmark runs only)
    # ------------------------------------------------------------------
    by_model = (
        df_runs.groupby('model', dropna=False)
        .agg(
            total_runs=('run_name', 'count'),
            distinct_run_names=('run_name', 'nunique'),
            distinct_benchmarks=('benchmark_group', 'nunique'),
            distinct_suite_versions=('suite_version', 'nunique'),
        )
        .reset_index()
        .sort_values('total_runs', ascending=False)
    )

    # ------------------------------------------------------------------
    # Per-benchmark-group breakdown (benchmark runs only)
    # ------------------------------------------------------------------
    by_benchmark = (
        df_runs.groupby('benchmark_group', dropna=False)
        .agg(
            total_runs=('run_name', 'count'),
            distinct_run_names=('run_name', 'nunique'),
            distinct_models=('model', 'nunique'),
            distinct_suite_versions=('suite_version', 'nunique'),
        )
        .reset_index()
        .sort_values('total_runs', ascending=False)
    )

    # ------------------------------------------------------------------
    # Duplicates by run_name (run names that appear in >1 row)
    # ------------------------------------------------------------------
    dup_groups = (
        df_runs.groupby('run_name')
        .agg(
            n_occurrences=('public_run_dir', 'count'),
            n_tracks=('public_track', 'nunique'),
            n_suite_versions=('suite_version', 'nunique'),
            n_distinct_hashes=('run_spec_hash', lambda s: s.dropna().nunique()),
            tracks=('public_track', lambda s: '|'.join(sorted(s.dropna().unique()))),
            suite_versions=('suite_version', lambda s: '|'.join(sorted(s.dropna().unique()))),
        )
        .reset_index()
    )
    duplicates = (
        dup_groups[dup_groups['n_occurrences'] > 1]
        .sort_values('n_occurrences', ascending=False)
    )

    # ------------------------------------------------------------------
    # Version drift: run names with >1 distinct run_spec_hash
    # ------------------------------------------------------------------
    drift_groups = (
        hash_df.groupby('run_name')
        .agg(
            n_distinct_hashes=('run_spec_hash', 'nunique'),
            n_occurrences=('public_run_dir', 'count'),
            n_suite_versions=('suite_version', 'nunique'),
            n_tracks=('public_track', 'nunique'),
            hashes=('run_spec_hash', lambda s: '|'.join(sorted(s.unique()))),
            suite_versions=('suite_version', lambda s: '|'.join(sorted(s.dropna().unique()))),
            tracks=('public_track', lambda s: '|'.join(sorted(s.dropna().unique()))),
        )
        .reset_index()
    )
    version_drift = (
        drift_groups[drift_groups['n_distinct_hashes'] > 1]
        .sort_values('n_distinct_hashes', ascending=False)
    )

    # ------------------------------------------------------------------
    # Build summary dict
    # ------------------------------------------------------------------
    top_models = (
        by_model.head(10)[['model', 'total_runs']]
        .to_dict(orient='records')
    )
    top_benchmarks = (
        by_benchmark.head(10)[['benchmark_group', 'total_runs']]
        .to_dict(orient='records')
    )

    summary: dict = {
        'index_fpath': str(index_fpath),
        'total_rows': total_rows,
        'n_benchmark_runs': n_benchmark_runs,
        'n_structural_non_run': n_structural_non_run,
        'n_unknown_entry': n_unknown_entry,
        'n_tracks': len(tracks),
        'tracks': tracks,
        'n_suite_versions': len(suite_versions),
        'suite_versions': suite_versions,
        'distinct_run_names': distinct_run_names,
        'distinct_models': distinct_models,
        'distinct_benchmark_groups': distinct_benchmarks,
        'distinct_scenario_classes': distinct_scenario_classes,
        'n_run_names_in_multiple_versions': n_run_names_multi_version,
        'n_run_names_in_multiple_tracks': n_run_names_multi_track,
        'n_run_names_with_hash_drift': n_run_names_with_hash_drift,
        'dedup_views': dedup_views,
        'top_models': top_models,
        'top_benchmarks': top_benchmarks,
    }

    # ------------------------------------------------------------------
    # Build summary text
    # ------------------------------------------------------------------
    summary_text = _format_summary_text(summary, df, tracks, suite_versions)

    # ------------------------------------------------------------------
    # Write artifacts
    # ------------------------------------------------------------------
    def _write_txt(text: str, name: str) -> Path:
        p = out_dpath / name
        p.write_text(text, encoding='utf-8')
        logger.success('Wrote {}', p)
        return p

    def _write_json(obj: dict, name: str) -> Path:
        p = out_dpath / name
        p.write_text(
            json.dumps(obj, indent=2, default=str, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )
        logger.success('Wrote {}', p)
        return p

    def _write_csv(df_out: pd.DataFrame, name: str) -> Path:
        p = out_dpath / name
        df_out.to_csv(p, index=False)
        logger.success('Wrote {}', p)
        return p

    _write_txt(summary_text, 'official_index_summary.latest.txt')
    _write_json(summary, 'official_index_summary.latest.json')
    _write_csv(by_track, 'official_index_by_track.latest.csv')
    _write_csv(by_suite, 'official_index_by_suite_version.latest.csv')
    _write_csv(by_model, 'official_index_by_model.latest.csv')
    _write_csv(by_benchmark, 'official_index_by_benchmark.latest.csv')
    _write_csv(duplicates, 'official_index_duplicates_by_run_name.latest.csv')
    _write_csv(version_drift, 'official_index_version_drift.latest.csv')

    print(summary_text)
    logger.success('Analysis complete — artifacts written to {}', out_dpath)
    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _agg_by_group(
    df: pd.DataFrame,
    df_runs: pd.DataFrame,
    group_col: str,
) -> pd.DataFrame:
    """Compute per-group breakdown combining all-rows and benchmark-runs-only counts."""
    total = df.groupby(group_col, dropna=False).size().rename('total_rows')
    runs = df_runs.groupby(group_col, dropna=False).size().rename('benchmark_runs')
    non_run = (
        df[df['entry_kind'] != 'benchmark_run']
        .groupby(group_col, dropna=False)
        .size()
        .rename('non_run_entries')
    )
    distinct_runs = (
        df_runs.groupby(group_col, dropna=False)['run_name']
        .nunique()
        .rename('distinct_run_names')
    )
    other_col = 'suite_version' if group_col == 'public_track' else 'public_track'
    cross = (
        df_runs.groupby(group_col, dropna=False)[other_col]
        .nunique()
        .rename(f'distinct_{other_col}s')
    )
    models = (
        df_runs.groupby(group_col, dropna=False)['model']
        .nunique()
        .rename('distinct_models')
    )
    result = (
        pd.concat([total, runs, non_run, distinct_runs, cross, models], axis=1)
        .fillna(0)
        .reset_index()
    )
    int_cols = [c for c in result.columns if c != group_col]
    result[int_cols] = result[int_cols].astype(int)
    return result


def _format_summary_text(
    summary: dict,
    df: pd.DataFrame,
    tracks: list[str],
    suite_versions: list[str],
) -> str:
    dv = summary['dedup_views']
    lines = [
        '=' * 70,
        'OFFICIAL/PUBLIC HELM INDEX — EXECUTIVE SUMMARY',
        '=' * 70,
        f"Index file: {summary['index_fpath']}",
        '',
        '--- Row counts ---',
        f"  Total rows:                {summary['total_rows']:>8,}",
        f"  Benchmark runs:            {summary['n_benchmark_runs']:>8,}",
        f"  Structural non-run:        {summary['n_structural_non_run']:>8,}",
        f"  Unknown entry kind:        {summary['n_unknown_entry']:>8,}",
        '',
        '--- Public tracks ---',
        f"  Number of tracks:          {summary['n_tracks']:>8}",
    ]
    for t in tracks:
        n = int((df['public_track'] == t).sum())
        lines.append(f'    {t}: {n:,}')
    lines += [
        '',
        '--- Suite versions ---',
        f"  Number of suite versions:  {summary['n_suite_versions']:>8}",
    ]
    for sv in suite_versions:
        n = int((df['suite_version'] == sv).sum())
        lines.append(f'    {sv}: {n:,}')
    lines += [
        '',
        '--- Diversity (benchmark runs only) ---',
        f"  Distinct run names:        {summary['distinct_run_names']:>8,}",
        f"  Distinct models:           {summary['distinct_models']:>8,}",
        f"  Distinct benchmark groups: {summary['distinct_benchmark_groups']:>8,}",
        f"  Distinct scenario classes: {summary['distinct_scenario_classes']:>8,}",
        '',
        '--- Version / track overlap ---',
        f"  Run names in >1 version:   {summary['n_run_names_in_multiple_versions']:>8,}",
        f"  Run names in >1 track:     {summary['n_run_names_in_multiple_tracks']:>8,}",
        f"  Run names with hash drift: {summary['n_run_names_with_hash_drift']:>8,}",
        '',
        '--- Deduplication views ---',
        f"  Raw benchmark-run rows:    {dv['raw_benchmark_run_rows']:>8,}",
        f"  Distinct run_name:         {dv['distinct_run_name']:>8,}",
        f"  Distinct (run_name,track): {dv['distinct_run_name_x_track']:>8,}",
        f"  Distinct run_spec_hash:    {dv['distinct_run_spec_hash']:>8,}",
        '',
        '--- Top 10 models by run count ---',
    ]
    for row in summary['top_models']:
        lines.append(f"  {row['model']}: {row['total_runs']:,}")
    lines += [
        '',
        '--- Top 10 benchmarks by run count ---',
    ]
    for row in summary['top_benchmarks']:
        lines.append(f"  {row['benchmark_group']}: {row['total_runs']:,}")
    lines.append('=' * 70)
    return '\n'.join(lines) + '\n'


__cli__ = AnalyzeOfficialIndexConfig

if __name__ == '__main__':
    setup_cli_logging()
    __cli__.main()
