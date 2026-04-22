from __future__ import annotations

import csv
import json
from pathlib import Path

from helm_audit.planning import core_report_planner
from helm_audit.workflows import plan_core_report_packets


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _make_run_spec(
    run_name: str,
    *,
    model: str = "meta/llama-3-8b",
    deployment: str = "local/meta-llama-3-8b",
    scenario_class: str = "helm.BoolQScenario",
    instructions: str | None = None,
) -> dict:
    adapter = {
        "model": model,
        "model_deployment": deployment,
        "max_eval_instances": 100,
    }
    if instructions is not None:
        adapter["instructions"] = instructions
    return {
        "name": run_name,
        "adapter_spec": adapter,
        "scenario_spec": {"class_name": scenario_class},
    }


def _setup_index_inputs(tmp_path: Path) -> tuple[Path, Path]:
    official_root = tmp_path / "official"
    local_root = tmp_path / "local"
    official_run = official_root / "benchmark_output" / "runs" / "v1" / "boolq:model=meta/llama-3-8b"
    local_run_a = local_root / "exp-a" / "helm" / "job-a" / "benchmark_output" / "runs" / "demo-suite" / "boolq:model=meta/llama-3-8b"
    local_run_b = local_root / "exp-a" / "helm" / "job-b" / "benchmark_output" / "runs" / "demo-suite" / "boolq:model=meta/llama-3-8b"
    for path in [official_run, local_run_a, local_run_b]:
        path.mkdir(parents=True, exist_ok=True)

    _write_json(
        official_run / "run_spec.json",
        _make_run_spec(
            "boolq:model=meta/llama-3-8b",
            deployment="hf/meta-llama-3-8b",
            instructions="official prompt",
        ),
    )
    _write_json(
        local_run_a / "run_spec.json",
        _make_run_spec(
            "boolq:model=meta/llama-3-8b",
            deployment="local/meta-llama-3-8b",
            instructions="local prompt",
        ),
    )
    _write_json(
        local_run_b / "run_spec.json",
        _make_run_spec(
            "boolq:model=meta/llama-3-8b",
            deployment="local/meta-llama-3-8b",
            instructions="local prompt",
        ),
    )

    local_index = tmp_path / "local_index.csv"
    official_index = tmp_path / "official_index.csv"
    _write_csv(
        local_index,
        [
            {
                "component_id": "local::exp-a::job-a::uuid-a",
                "source_kind": "local",
                "logical_run_key": "boolq:model=meta/llama-3-8b",
                "experiment_name": "exp-a",
                "job_id": "job-a",
                "job_dpath": str(local_run_a.parents[3]),
                "run_path": str(local_run_a),
                "run_spec_fpath": str(local_run_a / "run_spec.json"),
                "run_spec_name": "boolq:model=meta/llama-3-8b",
                "model": "meta/llama-3-8b",
                "model_deployment": "local/meta-llama-3-8b",
                "scenario_class": "helm.BoolQScenario",
                "benchmark_group": "boolq",
                "max_eval_instances": "100",
                "status": "computed",
                "manifest_timestamp": "20",
                "run_entry": "boolq:model=meta/llama-3-8b",
                "suite": "demo-suite",
                "attempt_uuid": "uuid-a",
                "attempt_identity": "uuid-a",
                "attempt_identity_kind": "attempt_uuid",
                "attempt_fallback_key": "fallback::job-a",
                "machine_host": "host-a",
            },
            {
                "component_id": "",
                "source_kind": "local",
                "logical_run_key": "boolq:model=meta/llama-3-8b",
                "experiment_name": "exp-a",
                "job_id": "job-b",
                "job_dpath": str(local_run_b.parents[3]),
                "run_path": str(local_run_b),
                "run_spec_fpath": str(local_run_b / "run_spec.json"),
                "run_spec_name": "boolq:model=meta/llama-3-8b",
                "model": "meta/llama-3-8b",
                "model_deployment": "local/meta-llama-3-8b",
                "scenario_class": "helm.BoolQScenario",
                "benchmark_group": "boolq",
                "max_eval_instances": "100",
                "status": "computed",
                "manifest_timestamp": "10",
                "run_entry": "boolq:model=meta/llama-3-8b",
                "suite": "demo-suite",
                "attempt_uuid": "",
                "attempt_identity": "",
                "attempt_identity_kind": "",
                "attempt_fallback_key": "fallback::job-b",
                "machine_host": "host-b",
            },
        ],
    )
    _write_csv(
        official_index,
        [
            {
                "component_id": "official::main::v1::boolq:model=meta/llama-3-8b",
                "source_kind": "official",
                "logical_run_key": "boolq:model=meta/llama-3-8b",
                "run_path": str(official_run),
                "public_run_dir": str(official_run),
                "run_name": "boolq:model=meta/llama-3-8b",
                "run_spec_fpath": str(official_run / "run_spec.json"),
                "run_spec_name": "boolq:model=meta/llama-3-8b",
                "model": "meta/llama-3-8b",
                "model_deployment": "hf/meta-llama-3-8b",
                "scenario_class": "helm.BoolQScenario",
                "benchmark_group": "boolq",
                "max_eval_instances": "100",
                "public_track": "main",
                "suite_version": "v1",
            }
        ],
    )
    return local_index, official_index


def test_planner_emits_packet_intent_for_one_official_one_local_case(tmp_path):
    local_index, official_index = _setup_index_inputs(tmp_path)
    artifact = core_report_planner.build_planning_artifact(
        local_index_fpath=local_index,
        official_index_fpath=official_index,
        experiment_name="exp-a",
        run_entry="boolq:model=meta/llama-3-8b",
    )

    assert artifact["packet_count"] == 1
    packet = artifact["packets"][0]
    assert packet["run_entry"] == "boolq:model=meta/llama-3-8b"
    assert {component["source_kind"] for component in packet["components"]} == {"local", "official"}
    assert any(comparison["comparison_kind"] == "official_vs_local" for comparison in packet["comparisons"])
    assert not any("kwdagger" in component["component_id"] for component in packet["components"])


def test_planner_emits_local_repeat_when_multiple_local_components_exist(tmp_path):
    local_index, official_index = _setup_index_inputs(tmp_path)
    artifact = core_report_planner.build_planning_artifact(
        local_index_fpath=local_index,
        official_index_fpath=official_index,
        experiment_name="exp-a",
        run_entry="boolq:model=meta/llama-3-8b",
    )

    comparison_kinds = [comparison["comparison_kind"] for comparison in artifact["packets"][0]["comparisons"]]
    assert "local_repeat" in comparison_kinds


def test_planner_preserves_stable_local_component_identity_using_uuid_or_fallback(tmp_path):
    local_index, official_index = _setup_index_inputs(tmp_path)
    artifact = core_report_planner.build_planning_artifact(
        local_index_fpath=local_index,
        official_index_fpath=official_index,
        experiment_name="exp-a",
        run_entry="boolq:model=meta/llama-3-8b",
    )

    local_components = [
        component
        for component in artifact["packets"][0]["components"]
        if component["source_kind"] == "local"
    ]
    component_by_id = {component["component_id"]: component for component in local_components}
    assert "local::exp-a::job-a::uuid-a" in component_by_id
    fallback_component = next(component for component in local_components if component["attempt_uuid"] is None)
    assert fallback_component["attempt_identity"] == "fallback::job-b"


def test_planner_writes_explicit_comparability_facts_and_caveats(tmp_path):
    local_index, official_index = _setup_index_inputs(tmp_path)
    artifact = core_report_planner.build_planning_artifact(
        local_index_fpath=local_index,
        official_index_fpath=official_index,
        experiment_name="exp-a",
        run_entry="boolq:model=meta/llama-3-8b",
    )

    packet = artifact["packets"][0]
    facts = packet["comparability_facts"]
    assert facts["same_model"]["status"] == "yes"
    assert facts["same_deployment"]["status"] == "no"
    assert facts["same_instructions"]["status"] == "no"
    assert any(item.startswith("comparability_drift:same_deployment") for item in packet["warnings"])
    assert any("same_instructions=no" in item for item in packet["caveats"])


def test_planner_outputs_are_human_inspectable_and_declared(tmp_path):
    local_index, official_index = _setup_index_inputs(tmp_path)
    out_dpath = tmp_path / "planned"

    plan_core_report_packets.main(
        [
            "--local-index-fpath", str(local_index),
            "--official-index-fpath", str(official_index),
            "--experiment-name", "exp-a",
            "--run-entry", "boolq:model=meta/llama-3-8b",
            "--out-dpath", str(out_dpath),
        ]
    )

    artifact = json.loads((out_dpath / "comparison_intents.latest.json").read_text())
    summary_text = (out_dpath / "comparison_intents.latest.txt").read_text()
    components_csv = (out_dpath / "comparison_intent_components.latest.csv").read_text()
    comparisons_csv = (out_dpath / "comparison_intent_comparisons.latest.csv").read_text()

    assert artifact["packet_count"] == 1
    assert "components:" in summary_text
    assert "comparisons:" in summary_text
    assert "comparability_facts:" in summary_text
    assert "component_id" in components_csv
    assert "comparison_kind" in comparisons_csv
