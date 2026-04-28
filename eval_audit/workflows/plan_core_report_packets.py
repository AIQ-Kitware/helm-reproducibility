from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from loguru import logger

import io as _io

from eval_audit.infra.fs_publish import write_text_atomic
from eval_audit.infra.logging import rich_link, setup_cli_logging
from eval_audit.planning.core_report_planner import (
    build_planning_artifact,
    comparison_rows,
    component_rows,
    packet_rows,
    planning_summary_lines,
    warning_rows,
    warning_summary_lines,
)


def _write_json(payload: Any, fpath: Path) -> None:
    write_text_atomic(fpath, json.dumps(payload, indent=2) + "\n")


def _write_text(lines: list[str], fpath: Path) -> None:
    write_text_atomic(fpath, "\n".join(lines).rstrip() + "\n")


def _write_csv(rows: list[dict[str, Any]], fpath: Path) -> None:
    fieldnames = sorted({key for row in rows for key in row.keys()}) if rows else []
    if not fieldnames:
        write_text_atomic(fpath, "")
        return
    buf = _io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    write_text_atomic(fpath, buf.getvalue())


def write_planning_outputs(*, artifact: dict[str, Any], out_dpath: Path) -> dict[str, Path]:
    out_dpath = out_dpath.expanduser().resolve()
    out_dpath.mkdir(parents=True, exist_ok=True)

    json_fpath = out_dpath / "comparison_intents.latest.json"
    txt_fpath = out_dpath / "comparison_intents.latest.txt"
    packet_csv_fpath = out_dpath / "comparison_intent_packets.latest.csv"
    component_csv_fpath = out_dpath / "comparison_intent_components.latest.csv"
    comparison_csv_fpath = out_dpath / "comparison_intent_comparisons.latest.csv"
    warnings_json_fpath = out_dpath / "warnings.latest.json"
    warnings_txt_fpath = out_dpath / "warnings.latest.txt"

    _write_json(artifact, json_fpath)
    _write_text(planning_summary_lines(artifact), txt_fpath)
    _write_csv(packet_rows(artifact), packet_csv_fpath)
    _write_csv(component_rows(artifact), component_csv_fpath)
    _write_csv(comparison_rows(artifact), comparison_csv_fpath)
    _write_json({"warnings": warning_rows(artifact)}, warnings_json_fpath)
    _write_text(warning_summary_lines(artifact), warnings_txt_fpath)

    return {
        "comparison_intents_json": json_fpath,
        "comparison_intents_txt": txt_fpath,
        "comparison_intent_packets_csv": packet_csv_fpath,
        "comparison_intent_components_csv": component_csv_fpath,
        "comparison_intent_comparisons_csv": comparison_csv_fpath,
        "warnings_json": warnings_json_fpath,
        "warnings_txt": warnings_txt_fpath,
    }


def main(argv: list[str] | None = None) -> None:
    setup_cli_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-index-fpath", required=True)
    parser.add_argument("--official-index-fpath", required=True)
    parser.add_argument("--experiment-name", default=None)
    parser.add_argument("--run-entry", default=None)
    parser.add_argument(
        "--official-eee-root",
        default=None,
        help=(
            "Root of prebuilt official HELM->EEE artifacts. Defaults to "
            "$AUDIT_STORE_ROOT/crfm-helm-public-eee-test when present."
        ),
    )
    parser.add_argument(
        "--local-eee-root",
        default=None,
        help="Root for canonical local HELM->EEE artifacts. Defaults to $AUDIT_STORE_ROOT/eee/local.",
    )
    parser.add_argument(
        "--ensure-local-eee",
        action="store_true",
        help="Convert selected local HELM runs to EEE when canonical local artifacts are missing.",
    )
    parser.add_argument("--out-dpath", required=True)
    args = parser.parse_args(argv)

    artifact = build_planning_artifact(
        local_index_fpath=args.local_index_fpath,
        official_index_fpath=args.official_index_fpath,
        experiment_name=args.experiment_name,
        run_entry=args.run_entry,
        official_eee_root=args.official_eee_root,
        local_eee_root=args.local_eee_root,
        ensure_local_eee=args.ensure_local_eee,
    )
    paths = write_planning_outputs(
        artifact=artifact,
        out_dpath=Path(args.out_dpath),
    )
    logger.info(f"Wrote comparison intents json: {rich_link(paths['comparison_intents_json'])}")
    logger.info(f"Wrote comparison intents text: {rich_link(paths['comparison_intents_txt'])}")
    logger.info(f"Wrote comparison intent packets csv: {rich_link(paths['comparison_intent_packets_csv'])}")
    logger.info(f"Wrote comparison intent components csv: {rich_link(paths['comparison_intent_components_csv'])}")
    logger.info(f"Wrote comparison intent comparisons csv: {rich_link(paths['comparison_intent_comparisons_csv'])}")
    logger.info(f"Wrote planner warnings json: {rich_link(paths['warnings_json'])}")
    logger.info(f"Wrote planner warnings text: {rich_link(paths['warnings_txt'])}")


if __name__ == "__main__":
    setup_cli_logging()
    main()
