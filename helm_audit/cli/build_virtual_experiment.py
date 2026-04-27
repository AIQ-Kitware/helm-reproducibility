"""Build a virtual experiment from a YAML manifest.

A virtual experiment is a declarative slice over existing audited runs
(plus, in a later iteration, externally-produced EEE artifacts). The
output is written outside the repo at the manifest's ``output.root``,
so derived results never pollute the checked-in tree.

Usage::

    helm-audit-build-virtual-experiment \
        --manifest configs/virtual-experiments/pythia-mmlu-stress.yaml \
        --ensure-local-eee \
        --allow-single-repeat
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from loguru import logger

from helm_audit.infra.logging import rich_link, setup_cli_logging
from helm_audit.virtual import (
    compose_virtual_experiment,
    load_manifest,
    write_synthesized_indexes,
)
from helm_audit.virtual.compose import provenance_payload
from helm_audit.workflows import analyze_experiment


def _copy_manifest(manifest_fpath: Path, dest_dpath: Path) -> Path:
    """Snapshot the manifest into the output dir for reproducibility."""
    dest_dpath.mkdir(parents=True, exist_ok=True)
    dest = dest_dpath / "manifest.yaml"
    shutil.copyfile(manifest_fpath, dest)
    return dest


def main(argv: list[str] | None = None) -> None:
    setup_cli_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Path to virtual-experiment YAML manifest.")
    parser.add_argument("--ensure-local-eee", action="store_true",
                        help="Convert local HELM runs to EEE on demand if canonical local artifacts are missing.")
    parser.add_argument("--allow-single-repeat", action="store_true",
                        help="Pass through to analyze_experiment so packets with one local component still build.")
    parser.add_argument("--official-eee-root", default=None)
    parser.add_argument("--local-eee-root", default=None)
    parser.add_argument("--compose-only", action="store_true",
                        help="Only synthesize index slices and write provenance; skip analysis. Useful for triage.")
    args = parser.parse_args(argv)

    manifest_fpath = Path(args.manifest).expanduser().resolve()
    manifest = load_manifest(manifest_fpath)
    logger.info(f"Loaded manifest: {rich_link(manifest_fpath)} (name={manifest.name!r})")

    output_root = manifest.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    indexes_dpath = output_root / "indexes"
    analysis_dpath = output_root / "analysis"

    # Snapshot the manifest as it was at compose time.
    saved_manifest = _copy_manifest(manifest_fpath, output_root)
    logger.info(f"Wrote manifest snapshot: {rich_link(saved_manifest)}")

    # Compose: filter sources by scope, stamp virtual experiment_name, etc.
    result = compose_virtual_experiment(manifest)
    logger.info(
        f"Composed virtual experiment '{manifest.name}': "
        f"{len(result.local_rows)} local rows retained "
        f"({result.discarded_local_count} discarded), "
        f"{len(result.official_rows)} official rows retained "
        f"({result.discarded_official_count} discarded), "
        f"{len(result.external_components)} external_eee components"
    )
    if result.external_components:
        logger.warning(
            f"{len(result.external_components)} external_eee components are recorded "
            "for provenance only; the planner does not yet consume them. They will be "
            "wired in by a later pass."
        )

    # Persist synthesized index slices + provenance.
    paths = write_synthesized_indexes(result, indexes_dpath=indexes_dpath)
    logger.info(f"Wrote synthesized audit index: {rich_link(paths['audit_index_fpath'])}")
    logger.info(f"Wrote synthesized official index: {rich_link(paths['official_index_fpath'])}")

    provenance_fpath = output_root / "provenance.json"
    provenance_fpath.write_text(json.dumps(provenance_payload(result), indent=2) + "\n")
    logger.info(f"Wrote provenance: {rich_link(provenance_fpath)}")

    if not result.local_rows:
        logger.warning(
            "No local rows retained after scope+include filters; analysis would be empty. "
            "Skipping analyze_experiment."
        )
        return

    if args.compose_only:
        logger.info("--compose-only set; skipping analyze_experiment.")
        return

    # Drive the existing analysis pipeline against the synthesized slice.
    analyze_argv: list[str] = [
        "--experiment-name", manifest.name,
        "--index-fpath", str(paths["audit_index_fpath"]),
        "--official-index-fpath", str(paths["official_index_fpath"]),
        "--analysis-dpath", str(analysis_dpath),
    ]
    if args.allow_single_repeat:
        analyze_argv.append("--allow-single-repeat")
    if args.ensure_local_eee:
        analyze_argv.append("--ensure-local-eee")
    if args.official_eee_root:
        analyze_argv.extend(["--official-eee-root", str(args.official_eee_root)])
    if args.local_eee_root:
        analyze_argv.extend(["--local-eee-root", str(args.local_eee_root)])

    logger.info(f"Running analyze_experiment over the virtual slice into {rich_link(analysis_dpath)}")
    analyze_experiment.main(analyze_argv)


if __name__ == "__main__":
    main()
