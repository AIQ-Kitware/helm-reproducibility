from __future__ import annotations

from helm_audit.workflows.build_reports_summary import (
    ATTEMPTED_LABEL,
    FILTER_SELECTION_EXCLUDED_LABEL,
    FILTER_SELECTION_SELECTED_LABEL,
    NOT_ATTEMPTED_LABEL,
    _build_off_story_summary,
    _build_attempted_to_repro_rows,
    _build_end_to_end_funnel_rows,
    _build_filter_to_attempt_rows,
    _build_filter_selection_by_model_rows,
    _build_run_multiplicity_summary,
)


def test_end_to_end_funnel_rows_cover_excluded_unrun_and_analyzed_cases():
    filter_inventory_rows = [
        {
            "run_spec_name": "bench:model=a",
            "selection_status": "excluded",
            "candidate_pool": "complete-run",
            "failure_reasons": ["too-large"],
            "is_structurally_incomplete": False,
        },
        {
            "run_spec_name": "bench:model=b",
            "selection_status": "selected",
            "candidate_pool": "complete-run",
            "failure_reasons": [],
            "is_structurally_incomplete": False,
        },
        {
            "run_spec_name": "bench:model=c",
            "selection_status": "selected",
            "candidate_pool": "complete-run",
            "failure_reasons": [],
            "is_structurally_incomplete": False,
        },
    ]
    scope_rows = [
        {
            "experiment_name": "demo-exp",
            "run_entry": "bench:model=c",
            "has_run_spec": "True",
            "status": "computed",
            "manifest_timestamp": "10",
        }
    ]
    repro_rows = [
        {
            "experiment_name": "demo-exp",
            "run_entry": "bench:model=c",
            "official_instance_agree_0": 1.0,
            "official_instance_agree_001": 1.0,
            "official_instance_agree_01": 1.0,
            "official_instance_agree_005": 1.0,
        }
    ]

    rows = _build_end_to_end_funnel_rows(
        filter_inventory_rows,
        scope_rows,
        repro_rows,
        tol_key="official_instance_agree_0",
    )
    excluded = next(row for row in rows if row.get("size_gate") == "excluded: exceeds size budget")
    assert "execution_stage" not in excluded
    assert "analysis_stage" not in excluded
    assert "reproduction_stage" not in excluded

    selected_rows = [row for row in rows if row.get("selection_gate") == FILTER_SELECTION_SELECTED_LABEL]
    unrun = next(row for row in selected_rows if row["execution_stage"] == "not_run_in_scope")
    analyzed = next(row for row in selected_rows if row["execution_stage"] == "completed_with_run_artifacts")

    assert "analysis_stage" not in unrun
    assert "reproduction_stage" not in unrun

    assert analyzed["analysis_stage"] == "analyzed"
    assert analyzed["reproduction_stage"] == "exact_or_near_exact"


def test_filter_to_attempt_rows_split_selected_and_attempted_states():
    filter_inventory_rows = [
        {
            "run_spec_name": "bench:model=a",
            "selection_status": "excluded",
            "candidate_pool": "complete-run",
            "failure_reasons": [],
            "is_structurally_incomplete": False,
        },
        {
            "run_spec_name": "bench:model=b",
            "selection_status": "selected",
            "candidate_pool": "eligible-model",
            "failure_reasons": [],
            "is_structurally_incomplete": False,
        },
        {
            "run_spec_name": "bench:model=c",
            "selection_status": "selected",
            "candidate_pool": "eligible-model",
            "failure_reasons": [],
            "is_structurally_incomplete": False,
        },
    ]
    scope_rows = [
        {
            "experiment_name": "demo-exp",
            "run_entry": "bench:model=c",
            "has_run_spec": "True",
            "status": "computed",
            "manifest_timestamp": "10",
        }
    ]

    rows = _build_filter_to_attempt_rows(filter_inventory_rows, scope_rows)
    excluded = next(row for row in rows if row.get("selection_gate") == FILTER_SELECTION_EXCLUDED_LABEL)
    assert "attempt_stage" not in excluded

    selected_rows = [row for row in rows if row.get("selection_gate") == FILTER_SELECTION_SELECTED_LABEL]
    assert {row["attempt_stage"] for row in selected_rows} == {ATTEMPTED_LABEL, NOT_ATTEMPTED_LABEL}


def test_filter_to_attempt_rows_surface_missing_model_metadata_explicitly():
    filter_inventory_rows = [
        {
            "run_spec_name": "cub200:model=openai/dalle-2",
            "selection_status": "excluded",
            "candidate_pool": "complete-run",
            "failure_reasons": ["missing-model-metadata"],
            "is_structurally_incomplete": False,
        },
    ]
    rows = _build_filter_to_attempt_rows(filter_inventory_rows, [])
    assert rows == [
        {
            "structural_gate": "kept: structurally complete",
            "metadata_gate": "excluded: missing model metadata",
        }
    ]


def test_attempted_to_repro_rows_start_from_attempted_runs_only():
    filter_inventory_rows = [
        {
            "run_spec_name": "bench:model=b",
            "selection_status": "selected",
            "candidate_pool": "eligible-model",
            "failure_reasons": [],
            "is_structurally_incomplete": False,
        },
        {
            "run_spec_name": "bench:model=c",
            "selection_status": "selected",
            "candidate_pool": "eligible-model",
            "failure_reasons": [],
            "is_structurally_incomplete": False,
        },
    ]
    scope_rows = [
        {
            "experiment_name": "demo-exp",
            "run_entry": "bench:model=c",
            "has_run_spec": "True",
            "status": "computed",
            "manifest_timestamp": "10",
        }
    ]
    repro_rows = [
        {
            "experiment_name": "demo-exp",
            "run_entry": "bench:model=c",
            "official_instance_agree_0": 1.0,
            "official_instance_agree_001": 1.0,
            "official_instance_agree_01": 1.0,
            "official_instance_agree_005": 1.0,
        }
    ]

    rows = _build_attempted_to_repro_rows(
        filter_inventory_rows,
        scope_rows,
        repro_rows,
        tol_key="official_instance_agree_0",
    )
    assert len(rows) == 1
    assert rows[0]["execution_stage"] == "completed_with_run_artifacts"
    assert rows[0]["analysis_stage"] == "analyzed"
    assert rows[0]["reproduction_stage"] == "exact_or_near_exact"


def test_filter_selection_by_model_rows_separate_selected_and_excluded_counts():
    rows = _build_filter_selection_by_model_rows(
        [
            {"model": "model-a", "selection_status": "selected"},
            {"model": "model-a", "selection_status": "excluded"},
            {"model": "model-a", "selection_status": "excluded"},
            {"model": "model-b", "selection_status": "selected"},
            {"model": "model-b", "selection_status": "selected"},
            {"model": "model-c", "selection_status": "excluded"},
        ]
    )

    assert rows == [
        {"model": "model-a", "selection_status": "excluded", "count": 2},
        {"model": "model-a", "selection_status": "selected", "count": 1},
        {"model": "model-b", "selection_status": "selected", "count": 2},
        {"model": "model-c", "selection_status": "excluded", "count": 1},
    ]


def test_off_story_summary_surfaces_stage_counts_and_registry_provenance():
    filter_inventory_rows = [
        {
            "run_spec_name": "bbh:model=openai/gpt-oss-20b",
            "model": "openai/gpt-oss-20b",
            "benchmark": "bbh",
            "scenario": "bbh",
            "selection_status": "selected",
            "expected_local_served": True,
            "replaces_helm_deployment": None,
            "local_registry_source": "preset:gpt_oss_20b_vllm",
        },
        {
            "run_spec_name": "mmlu:model=openai/gpt-oss-20b",
            "model": "openai/gpt-oss-20b",
            "benchmark": "mmlu",
            "scenario": "mmlu",
            "selection_status": "selected",
            "expected_local_served": True,
            "replaces_helm_deployment": None,
            "local_registry_source": "preset:gpt_oss_20b_vllm",
        },
        {
            "run_spec_name": "bbh:model=qwen/qwen2.5-7b-instruct-turbo",
            "model": "qwen/qwen2.5-7b-instruct-turbo",
            "benchmark": "bbh",
            "scenario": "bbh",
            "selection_status": "selected",
            "expected_local_served": True,
            "replaces_helm_deployment": "qwen/qwen2.5-7b-instruct-turbo",
            "local_registry_source": "preset:small_models_kubeai_overnight",
        },
    ]
    scope_rows = [
        {
            "experiment_name": "demo-exp",
            "run_entry": "bbh:model=openai/gpt-oss-20b",
            "model": "openai/gpt-oss-20b",
            "benchmark": "bbh",
            "has_run_spec": "True",
        },
        {
            "experiment_name": "demo-exp",
            "run_entry": "mmlu:model=openai/gpt-oss-20b",
            "model": "openai/gpt-oss-20b",
            "benchmark": "mmlu",
            "has_run_spec": "False",
        },
        {
            "experiment_name": "demo-exp",
            "run_entry": "bbh:model=qwen/qwen2.5-7b-instruct-turbo",
            "model": "qwen/qwen2.5-7b-instruct-turbo",
            "benchmark": "bbh",
            "has_run_spec": "True",
        },
    ]
    repro_rows = [
        {
            "experiment_name": "demo-exp",
            "run_entry": "bbh:model=openai/gpt-oss-20b",
        }
    ]

    summary = _build_off_story_summary(
        filter_inventory_rows=filter_inventory_rows,
        scope_rows=scope_rows,
        repro_rows=repro_rows,
    )

    assert summary["headline_counts"]["off_story"] == {
        "n_models": 1,
        "selected_run_entries": 2,
        "attempted_run_entries": 2,
        "completed_run_entries": 1,
        "analyzed_run_entries": 1,
    }
    assert summary["headline_counts"]["on_story"]["n_models"] == 1
    assert len(summary["rows"]) == 1
    row = summary["rows"][0]
    assert row["model"] == "openai/gpt-oss-20b"
    assert row["local_registry_source"] == "preset:gpt_oss_20b_vllm"
    assert row["replaces_helm_deployment"] is None
    assert row["n_selected_run_entries"] == 2
    assert row["n_attempted_run_entries"] == 2
    assert row["n_completed_run_entries"] == 1
    assert row["n_analyzed_run_entries"] == 1


def test_run_multiplicity_summary_tracks_attempt_identity_and_analysis_selection():
    filter_inventory_rows = [
        {
            "run_spec_name": "mmlu:model=openai/gpt-oss-20b",
            "model": "openai/gpt-oss-20b",
            "benchmark": "mmlu",
            "scenario": "mmlu",
            "selection_status": "selected",
            "expected_local_served": True,
            "replaces_helm_deployment": None,
            "local_registry_source": "preset:gpt_oss_20b_vllm",
        }
    ]
    scope_rows = [
        {
            "experiment_name": "exp-a",
            "job_id": "job-1",
            "run_entry": "mmlu:model=openai/gpt-oss-20b",
            "model": "openai/gpt-oss-20b",
            "benchmark": "mmlu",
            "machine_host": "host-a",
            "manifest_timestamp": "10",
            "has_run_spec": "True",
            "run_dir": "/runs/a1",
            "attempt_uuid": "uuid-a",
            "attempt_identity": "uuid-a",
            "attempt_identity_kind": "attempt_uuid",
            "attempt_fallback_key": "fallback::job-1",
        },
        {
            "experiment_name": "exp-a",
            "job_id": "job-2",
            "run_entry": "mmlu:model=openai/gpt-oss-20b",
            "model": "openai/gpt-oss-20b",
            "benchmark": "mmlu",
            "machine_host": "host-b",
            "manifest_timestamp": "20",
            "has_run_spec": "True",
            "run_dir": "/runs/a2",
            "attempt_uuid": "",
            "attempt_identity": "",
            "attempt_identity_kind": "",
            "attempt_fallback_key": "fallback::job-2",
        },
        {
            "experiment_name": "exp-b",
            "job_id": "job-3",
            "run_entry": "mmlu:model=openai/gpt-oss-20b",
            "model": "openai/gpt-oss-20b",
            "benchmark": "mmlu",
            "machine_host": "host-a",
            "manifest_timestamp": "30",
            "has_run_spec": "False",
            "run_dir": "/runs/a3",
            "attempt_uuid": "uuid-c",
            "attempt_identity": "uuid-c",
            "attempt_identity_kind": "attempt_uuid",
            "attempt_fallback_key": "fallback::job-3",
        },
    ]
    repro_rows = [
        {
            "experiment_name": "exp-a",
            "run_entry": "mmlu:model=openai/gpt-oss-20b",
            "analysis_selected_run_dirs": ["/runs/a1", "/runs/a2"],
            "report_dir": "/reports/r1",
        }
    ]

    summary = _build_run_multiplicity_summary(
        filter_inventory_rows=filter_inventory_rows,
        scope_rows=scope_rows,
        repro_rows=repro_rows,
    )

    assert summary["headline_counts"] == {
        "n_logical_runs": 1,
        "n_logical_runs_with_multiple_rows": 1,
        "n_logical_runs_with_multiple_completed_rows": 1,
        "n_logical_runs_with_multiple_analyzed_rows": 1,
        "n_logical_runs_with_ambiguous_analyzed_matching": 0,
        "n_logical_runs_spanning_multiple_machines": 1,
        "n_logical_runs_spanning_multiple_experiments": 1,
        "n_logical_runs_with_multiple_manifest_timestamps": 1,
        "n_logical_runs_with_multiple_attempt_ids": 1,
        "n_logical_runs_with_multiple_attempt_uuids": 1,
    }
    row = summary["rows"][0]
    assert row["logical_run_key"] == "mmlu:model=openai/gpt-oss-20b"
    assert row["n_rows"] == 3
    assert row["n_completed_rows"] == 2
    assert row["n_analyzed_rows"] == 2
    assert row["n_experiments"] == 2
    assert row["n_machines"] == 2
    assert row["n_attempt_ids"] == 3
    assert row["n_attempt_uuids"] == 2
    assert row["n_rows_without_attempt_uuid"] == 1
    assert row["latest_attempt_identity"] == "uuid-c"
    assert "fallback::job-2" in row["fallback_attempt_ids"]


def test_run_multiplicity_summary_marks_legacy_multi_completed_groups_ambiguous():
    filter_inventory_rows = [
        {
            "run_spec_name": "gsm8k:model=openai/gpt-oss-20b",
            "model": "openai/gpt-oss-20b",
            "benchmark": "gsm8k",
            "scenario": "gsm8k",
            "selection_status": "selected",
            "expected_local_served": True,
            "replaces_helm_deployment": None,
            "local_registry_source": "preset:gpt_oss_20b_vllm",
        }
    ]
    scope_rows = [
        {
            "experiment_name": "legacy-exp",
            "job_id": "job-1",
            "run_entry": "gsm8k:model=openai/gpt-oss-20b",
            "model": "openai/gpt-oss-20b",
            "benchmark": "gsm8k",
            "machine_host": "host-a",
            "manifest_timestamp": "10",
            "has_run_spec": "True",
            "run_dir": "/runs/g1",
            "attempt_fallback_key": "fallback::job-1",
        },
        {
            "experiment_name": "legacy-exp",
            "job_id": "job-2",
            "run_entry": "gsm8k:model=openai/gpt-oss-20b",
            "model": "openai/gpt-oss-20b",
            "benchmark": "gsm8k",
            "machine_host": "host-b",
            "manifest_timestamp": "20",
            "has_run_spec": "True",
            "run_dir": "/runs/g2",
            "attempt_fallback_key": "fallback::job-2",
        },
    ]
    repro_rows = [
        {
            "experiment_name": "legacy-exp",
            "run_entry": "gsm8k:model=openai/gpt-oss-20b",
            "report_dir": "/reports/legacy",
        }
    ]

    summary = _build_run_multiplicity_summary(
        filter_inventory_rows=filter_inventory_rows,
        scope_rows=scope_rows,
        repro_rows=repro_rows,
    )

    assert summary["headline_counts"]["n_logical_runs_with_ambiguous_analyzed_matching"] == 1
    row = summary["rows"][0]
    assert row["n_completed_rows"] == 2
    assert row["n_analyzed_rows"] == 0
    assert row["n_ambiguous_analyzed_candidates"] == 2
    assert row["analyzed_match_status_counts"]["ambiguous_legacy_group_multi_completed"] == 2
