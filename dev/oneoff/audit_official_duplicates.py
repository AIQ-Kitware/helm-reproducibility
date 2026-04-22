#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path
from collections import defaultdict


def iter_public_runs(public_root: Path):
    for track_dir in sorted(public_root.iterdir()):
        if not track_dir.is_dir():
            continue
        runs_root = track_dir / "benchmark_output" / "runs"
        if not runs_root.exists():
            continue
        for suite_version_dir in sorted(runs_root.iterdir()):
            if not suite_version_dir.is_dir():
                continue
            for run_dir in sorted(suite_version_dir.iterdir()):
                if not run_dir.is_dir():
                    continue
                yield {
                    "track": track_dir.name,
                    "suite_version": suite_version_dir.name,
                    "run_name": run_dir.name,
                    "run_dir": str(run_dir),
                }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--public-root",
        default="/data/crfm-helm-public",
        help="Root of public/offical HELM runs",
    )
    parser.add_argument("--only-multi", action="store_true")
    parser.add_argument("--as-json", action="store_true")
    args = parser.parse_args()

    public_root = Path(args.public_root)
    rows = list(iter_public_runs(public_root))

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["run_name"]].append(row)

    results = []
    for run_name, group in grouped.items():
        n_paths = len({g["run_dir"] for g in group})
        result = {
            "run_name": run_name,
            "n_rows": len(group),
            "n_distinct_paths": n_paths,
            "tracks": sorted({g["track"] for g in group}),
            "suite_versions": sorted({g["suite_version"] for g in group}),
            "paths": sorted(g["run_dir"] for g in group),
        }
        if not args.only_multi or n_paths > 1:
            results.append(result)

    results.sort(key=lambda r: (-r["n_distinct_paths"], r["run_name"]))

    if args.as_json:
        print(json.dumps(results, indent=2))
        return

    print(f"Scanned {len(rows)} public run directories under {public_root}")
    print(f"Reported {len(results)} grouped run names")
    print()

    for item in results[:200]:
        print("=" * 100)
        print(f"run_name:         {item['run_name']}")
        print(f"n_rows:           {item['n_rows']}")
        print(f"n_distinct_paths: {item['n_distinct_paths']}")
        print(f"tracks:           {item['tracks']}")
        print(f"suite_versions:   {item['suite_versions']}")
        print("paths:")
        for p in item["paths"]:
            print(f"  - {p}")


if __name__ == "__main__":
    main()
