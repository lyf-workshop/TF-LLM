from __future__ import annotations

import json
import subprocess
import sys

from utu.config import ConfigLoader
from utu.eval.experience_loader import ExperienceLoader
from utu.practice import hierarchical_ablation
from utu.practice.clustering_calibration import calibrate_training_l0
from utu.practice.experience_models import ExperienceRecord, stable_experience_id
from utu.practice.hierarchical_ablation import (
    build_ablation_report,
    build_three_group_report,
    prepare_ablation_seed,
)
from utu.skillsbench_data import assert_task_ids_disjoint, load_task_split_manifest


def test_skillsbench_ablation_configs_share_parameters_except_clustering_mode():
    baseline = ConfigLoader.load_training_free_grpo_config("skillsbench/skillsbench_hierarchy_ablation_a")
    clustered = ConfigLoader.load_training_free_grpo_config("skillsbench/skillsbench_hierarchy_ablation_b")
    baseline_hierarchy = baseline.practice.hierarchical_learning
    clustered_hierarchy = clustered.practice.hierarchical_learning
    assert baseline_hierarchy.clustering_enabled is False
    assert clustered_hierarchy.clustering_enabled is True
    assert baseline_hierarchy.random_seed == clustered_hierarchy.random_seed == 42
    assert baseline_hierarchy.aggregation_temperature == clustered_hierarchy.aggregation_temperature == 0.0
    assert baseline_hierarchy.min_l0_per_l1 == clustered_hierarchy.min_l0_per_l1 == 5
    assert baseline_hierarchy.min_l1_per_l2 == clustered_hierarchy.min_l1_per_l2 == 3


def test_experience_loader_accepts_legacy_dict_and_structured_list(tmp_path):
    path = tmp_path / "mixed_formats.json"
    path.write_text(
        json.dumps(
            {
                "l0_experiences": {"legacy-l0": "legacy content"},
                "l1_experiences": [
                    {
                        "id": "structured-l1",
                        "level": "L1",
                        "content": "structured content",
                        "parent_ids": ["legacy-l0"],
                    }
                ],
                "l2_experiences": {},
            }
        ),
        encoding="utf-8",
    )
    loaded = ExperienceLoader(path).load()
    assert [item.id for item in loaded] == ["structured-l1", "legacy-l0"]


def _record(content: str, index: int) -> dict:
    return ExperienceRecord(
        id=stable_experience_id("L0", content),
        level="L0",
        content=content,
        source_task_ids=[f"task-{index}"],
        failure_mode="timeout",
        task_stage="execute",
    ).public_dict()


def test_ablation_seed_uses_exact_l0_and_never_copies_upper_levels(tmp_path):
    source = tmp_path / "source.json"
    destination = tmp_path / "seed.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "l0_experiences": [
                    {**_record("alpha one", 1), "aggregation_status": "aggregated"},
                    {**_record("alpha two", 2), "aggregation_status": "aggregated"},
                ],
                "l1_experiences": [{"id": "old-l1", "content": "must not copy"}],
                "l2_experiences": [{"id": "old-l2", "content": "must not copy"}],
            }
        ),
        encoding="utf-8",
    )
    prepare_ablation_seed(source, destination)
    seeded = json.loads(destination.read_text(encoding="utf-8"))
    assert [item["content"] for item in seeded["l0_experiences"]] == ["alpha one", "alpha two"]
    assert all(item["aggregation_status"] == "pending" for item in seeded["l0_experiences"])
    assert seeded["l1_experiences"] == []
    assert seeded["l2_experiences"] == []
    assert len(seeded["source_snapshot_file_sha256"]) == 64
    assert len(seeded["source_l0_sha256"]) == 64


def test_ablation_report_allows_negative_downstream_result(tmp_path):
    baseline = tmp_path / "baseline.json"
    clustered = tmp_path / "clustered.json"
    baseline_audit = tmp_path / "baseline.jsonl"
    clustered_audit = tmp_path / "clustered.jsonl"
    baseline_eval = tmp_path / "baseline_eval.json"
    clustered_eval = tmp_path / "clustered_eval.json"
    records = [_record("alpha one", 1), _record("alpha two", 2)]
    for path, method in ((baseline, "sequential"), (clustered, "agglomerative")):
        path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "l0_experiences": records,
                    "l1_experiences": [],
                    "l2_experiences": [],
                }
            ),
            encoding="utf-8",
        )
        audit = baseline_audit if method == "sequential" else clustered_audit
        audit.write_text(
            json.dumps(
                {
                    "report": {
                        "clusters": [
                            {
                                "cluster_id": f"{method}-1",
                                "experience_ids": [item["id"] for item in records],
                                "intra_cluster_similarity": 0.9,
                                "metadata_consistency": 1.0,
                            }
                        ]
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
    baseline_eval.write_text(
        json.dumps([{"task_id": "1", "reward": 1}, {"task_id": "2", "reward": 1}]),
        encoding="utf-8",
    )
    clustered_eval.write_text(
        json.dumps([{"task_id": "1", "reward": 1}, {"task_id": "2", "reward": 0}]),
        encoding="utf-8",
    )

    report = build_ablation_report(
        baseline,
        clustered,
        baseline_audit=baseline_audit,
        clustered_audit=clustered_audit,
        baseline_eval=baseline_eval,
        clustered_eval=clustered_eval,
    )
    assert report["baseline_sequential"]["cluster_count"] == 1
    assert report["cluster_first"]["mean_intra_cluster_similarity"] == 0.9
    assert report["downstream"]["degraded_tasks"] == 1
    assert report["conclusion"] == "negative"


def test_evaluation_comparison_can_read_experiment_ids(monkeypatch):
    outcomes = {
        "baseline": {"task-1": 0.0, "task-2": 1.0},
        "clustered": {"task-1": 1.0, "task-2": 1.0},
    }
    monkeypatch.setattr(
        hierarchical_ablation,
        "_load_evaluation_from_db",
        lambda exp_id: outcomes[exp_id],
    )
    result = hierarchical_ablation.evaluation_comparison(
        None,
        None,
        baseline_exp_id="baseline",
        clustered_exp_id="clustered",
    )
    assert result["improved_tasks"] == 1
    assert result["degraded_tasks"] == 0


def test_skillsbench_manifest_inventory_and_transfer_splits():
    path = "configs/data/skillsbench/skillsbench_v1_1_task_splits.json"
    manifest = load_task_split_manifest(path)
    assert manifest["dataset"]["inventory_task_count"] == len(manifest["tasks"]) == 101
    assert all(
        {"task_id", "domain", "task_family", "required_tools", "required_capabilities"} <= set(task)
        for task in manifest["tasks"]
    )
    assert manifest["split_analysis"]["strict_all_task_types_holdout_feasible"] is False
    in_family = manifest["splits"]["in_family_v1"]
    assert not (set(in_family["train_task_ids"]) & set(in_family["eval_task_ids"]))
    assert set(in_family["train_families"]) == set(in_family["eval_families"])
    in_family_self_contained = manifest["splits"]["in_family_self_contained_v1"]
    assert len(in_family_self_contained["train_task_ids"]) == 37
    assert len(in_family_self_contained["eval_task_ids"]) == 35
    assert set(in_family_self_contained["train_families"]) == set(
        in_family_self_contained["eval_families"]
    )
    held_out = manifest["splits"]["family_holdout_self_contained_v1"]
    assert len(held_out["train_task_ids"]) == 40
    assert len(held_out["eval_task_ids"]) == 33
    assert not (set(held_out["train_task_ids"]) & set(held_out["eval_task_ids"]))
    assert not (set(held_out["train_families"]) & set(held_out["eval_families"]))


def test_skillsbench_overlap_assertion_is_fatal():
    import pytest

    with pytest.raises(ValueError, match="leakage"):
        assert_task_ids_disjoint(["task-a", "task-b"], ["task-b", "task-c"])


def test_calibration_waits_for_sufficient_new_format_training_l0(tmp_path):
    manifest_path = "configs/data/skillsbench/skillsbench_v1_1_task_splits.json"
    manifest = load_task_split_manifest(manifest_path)
    train_ids = manifest["splits"]["family_holdout_self_contained_v1"]["train_task_ids"][:2]
    records = [
        ExperienceRecord(
            id=stable_experience_id("L0", f"lesson {index}"),
            level="L0",
            content=f"lesson {index}",
            source_task_ids=[f"SkillsBench:{task_id}"],
            task_family="implementation",
        ).public_dict()
        for index, task_id in enumerate(train_ids)
    ]
    hierarchy = tmp_path / "training_l0.json"
    hierarchy.write_text(json.dumps({"l0_experiences": records}), encoding="utf-8")
    report = calibrate_training_l0(
        hierarchy,
        manifest_path,
        "family_holdout_self_contained_v1",
        embedding_provider=None,
        thresholds=[0.5, 0.6],
    )
    assert report["status"] == "waiting_for_data"
    assert report["recommended_threshold"] is None
    assert report["evidence"]["eligible_training_l0"] == 2


def test_three_group_report_is_paired_and_allows_clustered_regression(tmp_path):
    manifest_path = "configs/data/skillsbench/skillsbench_v1_1_task_splits.json"
    split_name = "family_holdout_self_contained_v1"
    manifest = load_task_split_manifest(manifest_path)
    task_ids = manifest["splits"][split_name]["eval_task_ids"]
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps({"l0_experiences": [_record("alpha one", 1), _record("alpha two", 2)]}),
        encoding="utf-8",
    )
    sequential = tmp_path / "sequential.json"
    clustered = tmp_path / "clustered.json"
    prepare_ablation_seed(source, sequential)
    prepare_ablation_seed(source, clustered)

    evaluation_paths = {}
    pass_sets = {
        "no_experience": {task_ids[0], task_ids[1]},
        "sequential": {task_ids[0], task_ids[1], task_ids[2]},
        "clustered": {task_ids[0]},
    }
    token_counts = {"no_experience": 0, "sequential": 10, "clustered": 8}
    for condition in ("no_experience", "sequential", "clustered"):
        rows = []
        for task_id in task_ids:
            rows.append(
                {
                    "task_id": task_id,
                    "reward": 1.0 if task_id in pass_sets[condition] else 0.0,
                    "meta": {
                        "model_config_sha256": "same-model-hash",
                        "requested_model": "offline-mock",
                        "temperature": 0.0,
                        "expected_trials_per_task": 1,
                        "task_split_name": split_name,
                        "train_dataset_for_overlap_check": "train-dataset",
                        "experience_condition": condition,
                        "injected_token_count": token_counts[condition],
                        "injected_tokenizer": "cl100k_base",
                    },
                }
            )
        path = tmp_path / f"{condition}_evaluation.json"
        path.write_text(json.dumps(rows), encoding="utf-8")
        evaluation_paths[condition] = path

    report = build_three_group_report(
        evaluation_paths=evaluation_paths,
        evaluation_exp_ids=None,
        sequential_hierarchy=sequential,
        clustered_hierarchy=clustered,
        split_manifest_path=manifest_path,
        split_name=split_name,
    )
    assert report["integrity"]["identical_task_order"] is True
    assert report["integrity"]["runtime_parameter_verification"]["status"] == "verified"
    assert report["groups"]["sequential"]["passes"] == 3
    assert report["groups"]["clustered"]["passes"] == 1
    assert report["pairwise_vs_no_experience"]["sequential"]["experience_win"] == 1
    assert report["pairwise_vs_no_experience"]["clustered"]["baseline_win"] == 1
    assert report["conclusion"] == "highest_observed_pass_rate:sequential"


def test_three_group_plan_only_never_runs_aggregation(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps({"l0_experiences": [_record("offline seed one", 1), _record("offline seed two", 2)]}),
        encoding="utf-8",
    )
    output_dir = tmp_path / "plan"
    subprocess.run(
        [
            sys.executable,
            "scripts/experiments/run_hierarchical_ablation.py",
            "--config-name",
            "skillsbench/skillsbench_practice",
            "--source-experiences",
            str(source),
            "--output-dir",
            str(output_dir),
            "--plan-only",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    plan = json.loads((output_dir / "experiment_plan.json").read_text(encoding="utf-8"))
    assert plan["conditions"] == ["no_experience", "sequential", "clustered"]
    assert plan["status"] == "plan_only"
    assert len(plan["eval_task_ids"]) == 33
    assert not (output_dir / "sequential.json").exists()
    assert not (output_dir / "clustered.json").exists()
