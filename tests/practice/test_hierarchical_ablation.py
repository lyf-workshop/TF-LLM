from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from argparse import Namespace
from types import SimpleNamespace

import pytest

from scripts import run_eval
from scripts.experiments import (
    calibrate_hierarchical_clustering as calibration_cli,
    run_hierarchical_ablation as ablation_cli,
)
from utu.config import ConfigLoader
from utu.config.practice_config import HierarchicalLearningConfig
from utu.db import DatasetSample
from utu.eval.data.data_manager import DBDataManager
from utu.eval.experience_loader import ExperienceLoader
from utu.practice import hierarchical_ablation
from utu.practice.clustering_calibration import calibrate_training_l0, calibrate_training_l1
from utu.practice.experience_clusterer import ExperienceClusterer
from utu.practice.experience_models import ExperienceRecord, stable_experience_id
from utu.practice.hierarchical_ablation import (
    build_ablation_report,
    build_three_group_report,
    config_sha256,
    file_sha256,
    hierarchy_metrics,
    prepare_ablation_seed,
    sign_experiment_protocol,
)
from utu.skillsbench_data import (
    assert_task_ids_disjoint,
    canonical_sha256,
    load_task_split_manifest,
)


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


class _FamilyEmbedding:
    def embed(self, texts):
        return [[1.0, 0.0] if "alpha" in text else [0.0, 1.0] for text in texts]

    def info(self):
        return {"provider": "deterministic-test"}


class _EquidistantEmbedding:
    """Give every distinct numbered sample cosine similarity exactly 0.8."""

    def embed(self, texts):
        vectors = []
        for text in texts:
            sample_index = int(text.rsplit("-", 1)[-1])
            vector = [math.sqrt(0.8), 0.0, 0.0, 0.0, 0.0]
            vector[sample_index + 1] = math.sqrt(0.2)
            vectors.append(vector)
        return vectors

    def info(self):
        return {"provider": "equidistant-test"}


def test_layered_provisional_flags_preserve_legacy_config_semantics():
    defaults = HierarchicalLearningConfig()
    assert defaults.l0_similarity_threshold_provisional is True
    assert defaults.l1_similarity_threshold_provisional is True
    assert defaults.similarity_thresholds_provisional is None

    legacy_open = HierarchicalLearningConfig(similarity_thresholds_provisional=False)
    assert legacy_open.l0_similarity_threshold_provisional is False
    assert legacy_open.l1_similarity_threshold_provisional is False

    layered = HierarchicalLearningConfig(
        l0_similarity_threshold_provisional=False,
        l1_similarity_threshold_provisional=True,
    )
    assert layered.l0_similarity_threshold_provisional is False
    assert layered.l1_similarity_threshold_provisional is True

    legacy_wins_when_mixed = HierarchicalLearningConfig(
        l0_similarity_threshold_provisional=False,
        similarity_thresholds_provisional=True,
    )
    assert legacy_wins_when_mixed.l0_similarity_threshold_provisional is True
    assert legacy_wins_when_mixed.l1_similarity_threshold_provisional is True


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
    assert report["readiness"]["policy"] == "conservative_training_proxy"
    assert report["readiness"]["minimum_records"] == 20
    assert report["readiness"]["minimum_positive_pairs"] == 10
    assert report["readiness"]["minimum_negative_pairs"] == 10


def test_calibration_rejects_source_namespace_mismatch(tmp_path):
    task_lists = {
        "train_task_ids": ["task-1"],
        "eval_task_ids": [],
        "excluded_task_ids": [],
    }
    manifest = {
        "dataset": {"name": "ExpectedDataset", "namespace": "ExpectedDataset"},
        "splits": {
            "train_only": {
                **task_lists,
                "split_sha256": canonical_sha256(task_lists),
            }
        },
    }
    manifest_path = tmp_path / "split.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    record = ExperienceRecord(
        id=stable_experience_id("L0", "namespace-sensitive lesson"),
        level="L0",
        content="namespace-sensitive lesson",
        source_task_ids=["OtherDataset:task-1"],
        task_family="implementation",
    )
    hierarchy_path = tmp_path / "hierarchy.json"
    hierarchy_path.write_text(
        json.dumps({"l0_experiences": [record.public_dict()]}),
        encoding="utf-8",
    )

    report = calibrate_training_l0(
        hierarchy_path,
        manifest_path,
        "train_only",
        embedding_provider=None,
        thresholds=[0.5],
        min_records=2,
        min_positive_pairs=1,
        min_negative_pairs=1,
    )

    assert report["status"] == "waiting_for_data"
    assert report["evidence"]["eligible_training_l0"] == 0
    assert report["evidence"]["outside_train_records"] == {}
    assert report["evidence"]["expected_source_namespace"] == "ExpectedDataset"
    assert report["evidence"]["source_namespace_mismatches"] == {
        record.id: ["OtherDataset:task-1"]
    }
    assert any("different dataset namespace" in reason for reason in report["reasons"])


def test_l1_default_readiness_is_minimum_analyzable_and_requires_both_pair_types(
    tmp_path,
):
    manifest_path = "configs/data/skillsbench/skillsbench_v1_1_task_splits.json"
    manifest = load_task_split_manifest(manifest_path)
    train_ids = manifest["splits"]["family_holdout_self_contained_v1"]["train_task_ids"][:8]
    hierarchy = tmp_path / "l1_readiness.json"

    def records(families):
        result = []
        for index, (task_id, family) in enumerate(zip(train_ids, families, strict=True)):
            prefix = "alpha" if index < 4 else "beta"
            parent_id = f"L0_readiness_parent_{index}"
            result.append(
                ExperienceRecord(
                    id=stable_experience_id("L1", f"{prefix} lesson {index}", [parent_id]),
                    level="L1",
                    content=f"{prefix} lesson {index}",
                    source_task_ids=[f"SkillsBench:{task_id}"],
                    parent_ids=[parent_id],
                    source_l0_ids=[parent_id],
                    task_family=family,
                ).public_dict()
            )
        return result

    hierarchy.write_text(
        json.dumps({"l1_experiences": records(["same-family"] * 8)}),
        encoding="utf-8",
    )
    no_negative_pairs = calibrate_training_l1(
        hierarchy,
        manifest_path,
        "family_holdout_self_contained_v1",
        embedding_provider=None,
        thresholds=[0.5],
    )
    assert no_negative_pairs["status"] == "waiting_for_data"
    assert no_negative_pairs["readiness"]["minimum_records"] == 8
    assert no_negative_pairs["readiness"]["minimum_positive_pairs"] == 3
    assert no_negative_pairs["readiness"]["minimum_negative_pairs"] == 6
    assert no_negative_pairs["readiness"]["observed_negative_pairs"] == 0
    assert any("different-family pairs" in reason for reason in no_negative_pairs["reasons"])

    hierarchy.write_text(
        json.dumps({"l1_experiences": records([f"family-{index}" for index in range(8)])}),
        encoding="utf-8",
    )
    no_positive_pairs = calibrate_training_l1(
        hierarchy,
        manifest_path,
        "family_holdout_self_contained_v1",
        embedding_provider=None,
        thresholds=[0.5],
    )
    assert no_positive_pairs["status"] == "waiting_for_data"
    assert no_positive_pairs["readiness"]["observed_positive_pairs"] == 0
    assert any("same-family pairs" in reason for reason in no_positive_pairs["reasons"])

    hierarchy.write_text(
        json.dumps({"l1_experiences": records(["family-a"] * 4 + ["family-b"] * 4)}),
        encoding="utf-8",
    )
    analyzable = calibrate_training_l1(
        hierarchy,
        manifest_path,
        "family_holdout_self_contained_v1",
        embedding_provider=_FamilyEmbedding(),
        thresholds=[0.5],
    )
    assert analyzable["status"] == "calibrated_training_proxy"
    assert analyzable["readiness"]["policy"] == "minimum_analyzable_not_sufficient"
    assert analyzable["readiness"]["is_statistical_sufficiency_claim"] is False
    assert all(analyzable["readiness"]["uses_layer_defaults"].values())


def test_calibration_cli_exposes_readiness_overrides(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "calibrate_hierarchical_clustering.py",
            "--experiences",
            "unused.json",
            "--level",
            "L1",
            "--min-records",
            "7",
            "--min-positive-pairs",
            "2",
            "--min-negative-pairs",
            "5",
            "--hard-constraint-fields",
            "task_stage",
            "failure_mode",
            "--soft-constraint-fields",
            "domain",
            "task_family",
            "tool_type",
        ],
    )
    args = calibration_cli.parse_args()
    assert args.min_records == 7
    assert args.min_positive_pairs == 2
    assert args.min_negative_pairs == 5
    assert args.hard_constraint_fields == ["task_stage", "failure_mode"]
    assert args.soft_constraint_fields == ["domain", "task_family", "tool_type"]


def test_l1_calibration_uses_only_active_training_records(tmp_path):
    manifest_path = "configs/data/skillsbench/skillsbench_v1_1_task_splits.json"
    manifest = load_task_split_manifest(manifest_path)
    split = manifest["splits"]["family_holdout_self_contained_v1"]
    train_ids = split["train_task_ids"][:4]

    def l1_record(content, task_id, family, index, *, lifecycle_status="active"):
        parent_id = f"L0_parent_{index}"
        return ExperienceRecord(
            id=stable_experience_id("L1", content, [parent_id]),
            level="L1",
            content=content,
            source_task_ids=[f"SkillsBench:{task_id}"],
            parent_ids=[parent_id],
            source_l0_ids=[parent_id],
            task_family=family,
            lifecycle_status=lifecycle_status,
        ).public_dict()

    records = [
        l1_record("alpha procedure one", train_ids[0], "family-a", 0),
        l1_record("alpha procedure two", train_ids[1], "family-a", 1),
        l1_record("beta procedure one", train_ids[2], "family-b", 2),
        l1_record("beta procedure two", train_ids[3], "family-b", 3),
        l1_record(
            "alpha stale evaluation procedure",
            split["eval_task_ids"][0],
            "family-a",
            4,
            lifecycle_status="needs_review",
        ),
    ]
    hierarchy = tmp_path / "training_l1.json"
    hierarchy.write_text(json.dumps({"l1_experiences": records}), encoding="utf-8")

    report = calibrate_training_l1(
        hierarchy,
        manifest_path,
        "family_holdout_self_contained_v1",
        embedding_provider=_FamilyEmbedding(),
        thresholds=[0.5],
        min_records=4,
        min_positive_pairs=2,
        min_negative_pairs=4,
    )

    assert report["status"] == "calibrated_training_proxy"
    assert report["source_level"] == "L1"
    assert report["threshold_config_field"] == "l1_similarity_threshold"
    assert report["provisional_config_field"] == "l1_similarity_threshold_provisional"
    assert report["evidence"]["eligible_training_l1"] == 4
    assert len(report["evidence"]["excluded_non_active_l1_ids"]) == 1
    assert report["pair_similarity"]["positive_same_task_family"]["count"] == 2
    assert report["pair_similarity"]["negative_different_task_family"]["count"] == 4
    assert report["threshold_sweep"][0]["cluster_sizes"] == [2, 2]
    assert report["threshold_sweep"][0]["pending_ratio"] == 1.0

    records[-1]["lifecycle_status"] = "active"
    hierarchy.write_text(json.dumps({"l1_experiences": records}), encoding="utf-8")
    with pytest.raises(ValueError, match="formal evaluation task evidence"):
        calibrate_training_l1(
            hierarchy,
            manifest_path,
            "family_holdout_self_contained_v1",
            embedding_provider=None,
            thresholds=[0.5],
            min_records=4,
            min_positive_pairs=2,
            min_negative_pairs=4,
        )


def test_calibration_uses_runtime_adjusted_score_and_reports_task_family_circularity(
    tmp_path,
):
    manifest_path = "configs/data/skillsbench/skillsbench_v1_1_task_splits.json"
    manifest = load_task_split_manifest(manifest_path)
    train_ids = manifest["splits"]["family_holdout_self_contained_v1"]["train_task_ids"][:4]
    records = []
    for index, task_id in enumerate(train_ids):
        parent_id = f"L0_pair_score_parent_{index}"
        content = f"procedure-{index}"
        records.append(
            ExperienceRecord(
                id=stable_experience_id("L1", content, [parent_id]),
                level="L1",
                content=content,
                source_task_ids=[f"SkillsBench:{task_id}"],
                parent_ids=[parent_id],
                source_l0_ids=[parent_id],
                domain="math",
                task_family="family-a" if index < 2 else "family-b",
            ).public_dict()
        )
    hierarchy = tmp_path / "pair_score_contract.json"
    hierarchy.write_text(json.dumps({"l1_experiences": records}), encoding="utf-8")

    report = calibrate_training_l1(
        hierarchy,
        manifest_path,
        "family_holdout_self_contained_v1",
        embedding_provider=_EquidistantEmbedding(),
        thresholds=[0.81],
        min_cluster_size=2,
        min_records=4,
        min_positive_pairs=2,
        min_negative_pairs=4,
        soft_constraint_fields=["domain", "task_family"],
    )

    contract = report["score_contract"]
    runtime_contract = ExperienceClusterer(
        _EquidistantEmbedding(),
        hard_constraint_fields=["task_stage", "failure_mode"],
        soft_constraint_fields=["domain", "task_family"],
    ).pair_score_contract()
    assert {key: contract[key] for key in runtime_contract} == runtime_contract
    assert contract["shared_runtime_pair_score_api"] is True
    assert contract["threshold_score"] == "adjusted_similarity"
    assert contract["requested_soft_constraint_fields"] == ["domain", "task_family"]
    assert contract["soft_constraint_fields"] == ["domain", "task_family"]
    assert contract["excluded_soft_constraint_fields"] == []
    assert contract["proxy_label_used_as_score_feature"] is True
    assert contract["circularity_warning"]["applies"] is True
    assert contract["circularity_warning"]["requires_human_review"] is True
    assert report["warnings"] == [contract["circularity_warning"]]
    assert report["pair_similarity"]["raw_cosine"]["positive_same_task_family"][
        "mean"
    ] == pytest.approx(0.8)
    assert report["pair_similarity"]["raw_cosine"]["negative_different_task_family"][
        "mean"
    ] == pytest.approx(0.8)
    assert report["pair_similarity"]["positive_same_task_family"]["mean"] == pytest.approx(
        0.82
    )
    assert report["pair_similarity"]["negative_different_task_family"][
        "mean"
    ] == pytest.approx(0.76)
    # The sweep invokes the same runtime clusterer contract: same-family pairs
    # receive the configured soft match while different-family pairs receive
    # the configured mismatch penalty. The report warns this proxy score is
    # circular and cannot be accepted without inspecting real cluster samples.
    assert report["threshold_sweep"][0]["cluster_sizes"] == [2, 2]
    assert report["threshold_sweep"][0]["pending_ratio"] == 0.0


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
    assert plan["report_command"][:2] == [
        "python",
        "scripts/experiments/report_hierarchical_ablation.py",
    ]
    assert not (output_dir / "sequential.json").exists()
    assert not (output_dir / "clustered.json").exists()


def test_strict_math_manifest_plan_is_static_and_marks_eval_order_unavailable(tmp_path):
    task_lists = {
        "train_task_ids": ["0"],
        "eval_task_ids": [],
        "excluded_task_ids": [],
    }
    manifest = {
        "schema_version": 3,
        "target_dataset": "DAPO-v3-test",
        "target_dataset_sha256": "a" * 64,
        "dataset": {"name": "DAPO-v3-test", "namespace": "DAPO-v3-test", "version": "v3"},
        "tasks": [{"task_id": "0"}],
        "splits": {
            "training": {
                **task_lists,
                "split_sha256": canonical_sha256(task_lists),
            }
        },
        "evaluation_exclusion": {
            "dataset": "AIME24-test",
            "record_count": 2,
            "snapshot_sha256": "b" * 64,
        },
    }
    manifest["dataset"]["inventory_sha256"] = canonical_sha256(manifest["tasks"])
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    manifest_path = tmp_path / "dapo_v3.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    config = SimpleNamespace(
        data=SimpleNamespace(
            require_practice_manifest=True,
            practice_manifest_path=str(manifest_path),
            practice_manifest_split="training",
            practice_manifest_expected_records=1,
            practice_dataset_name="DAPO-v3-test",
        ),
        evaluation=SimpleNamespace(data=SimpleNamespace(dataset="AIME24-test")),
    )

    training, evaluation = ablation_cli._static_training_contract(config)

    assert training["validation_mode"] == "strict_practice_manifest"
    assert training["task_ids"] == ["DAPO-v3-test:0"]
    assert evaluation["record_count"] == 2
    assert evaluation["snapshot_sha256"] == "b" * 64
    assert evaluation["task_order"] == []
    assert evaluation["inventory_availability"] == "requires_execute_database_validation"


def test_db_data_manager_enforces_signed_namespaced_order():
    config = ConfigLoader.load_eval_config("math/math_AIME24")
    order = ["AIME24:1", "AIME24:0"]
    config.data.task_order = order
    config.data.task_order_sha256 = canonical_sha256(order)
    manager = object.__new__(DBDataManager)
    manager.config = config
    rows = [
        DatasetSample(dataset="AIME24", index=0, question="zero"),
        DatasetSample(dataset="AIME24", index=1, question="one"),
    ]

    assert [row.index for row in manager._order_datapoints(rows)] == [1, 0]
    config.data.task_order = ["AIME24:1"]
    config.data.task_order_sha256 = canonical_sha256(config.data.task_order)
    with pytest.raises(ValueError, match="differs from signed task_order"):
        manager._order_datapoints(rows)


def _protocol_report_fixture(tmp_path, *, pass_k=2):
    source = tmp_path / "source_protocol.json"
    source.write_text(json.dumps({"l0_experiences": [_record("protocol lesson", 1)]}), encoding="utf-8")
    sequential = tmp_path / "sequential_protocol.json"
    clustered = tmp_path / "clustered_protocol.json"
    prepare_ablation_seed(source, sequential)
    prepare_ablation_seed(source, clustered)
    sequential_audit = tmp_path / "sequential_protocol.jsonl"
    clustered_audit = tmp_path / "clustered_protocol.jsonl"
    sequential_audit.write_text("", encoding="utf-8")
    clustered_audit.write_text("", encoding="utf-8")
    source_hash = json.loads(sequential.read_text(encoding="utf-8"))["source_l0_sha256"]
    tasks = [
        {
            "task_id": f"AIME24:{index}",
            "namespaced_task_id": f"AIME24:{index}",
            "dataset_index": index,
            "question_sha256": str(index) * 64,
            "domain": "mathematics",
            "task_family": None,
        }
        for index in range(2)
    ]
    task_order = [task["namespaced_task_id"] for task in tasks]
    conditions = {}
    token_counts = {"no_experience": 0, "sequential": 11, "clustered": 9}
    for condition in ("no_experience", "sequential", "clustered"):
        conditions[condition] = {
            "agent_config_sha256": f"agent-{condition}",
            "prompt_sha256": f"prompt-{condition}",
            "declared_injected_token_count": token_counts[condition],
            "injected_tokenizer": "cl100k_base",
            "expected_exp_id": f"exp-{condition}",
        }
    conditions["sequential"]["hierarchy_file_sha256"] = file_sha256(sequential)
    conditions["clustered"]["hierarchy_file_sha256"] = file_sha256(clustered)
    conditions["sequential"]["audit_file_sha256"] = file_sha256(sequential_audit)
    conditions["clustered"]["audit_file_sha256"] = file_sha256(clustered_audit)
    protocol = sign_experiment_protocol(
        {
            "schema_version": "three-condition-v2",
            "status": "ready",
            "conditions": ["no_experience", "sequential", "clustered"],
            "source_l0": {"source_l0_sha256": source_hash},
            "training": {
                "dataset": "DAPO-v3-test",
                "split_name": "training",
                "split_sha256": "split-hash",
            },
            "evaluation": {
                "dataset": "AIME24",
                "record_count": 2,
                "snapshot_sha256": "snapshot-hash",
                "inventory_sha256": canonical_sha256(tasks),
                "tasks": tasks,
                "task_order": task_order,
                "task_order_sha256": canonical_sha256(task_order),
                "result_task_order": task_order,
                "result_task_order_sha256": canonical_sha256(task_order),
                "resolved_config_sha256": "eval-config-hash",
            },
            "shared_parameters": {
                "pass_k": pass_k,
                "model_config_sha256": "model-hash",
            },
            "condition_configs": conditions,
        }
    )
    protocol_path = tmp_path / "experiment_protocol.json"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    paths = {}
    for condition in conditions:
        rows = []
        for index in range(2):
            for trial_index in range(pass_k):
                rows.append(
                    {
                        "dataset": "AIME24",
                        "dataset_index": index,
                        "stage": "judged",
                        "reward": float(index == 0),
                        "meta": {
                            "trial_index": trial_index,
                            "model_config_sha256": "model-hash",
                            "agent_config_sha256": conditions[condition]["agent_config_sha256"],
                            "prompt_sha256": conditions[condition]["prompt_sha256"],
                            "requested_model": "offline-model",
                            "temperature": 0.0,
                            "expected_trials_per_task": pass_k,
                            "task_split_name": "training",
                            "train_dataset_for_overlap_check": "DAPO-v3-test",
                            "injected_tokenizer": "cl100k_base",
                            "injected_token_count": token_counts[condition],
                            "experience_condition": condition,
                            "experiment_protocol_sha256": protocol["protocol_sha256"],
                            "evaluation_config_sha256": "eval-config-hash",
                            "task_order_sha256": canonical_sha256(task_order),
                        },
                    }
                )
        path = tmp_path / f"{condition}_protocol_results.json"
        path.write_text(json.dumps(rows), encoding="utf-8")
        paths[condition] = path
    return protocol_path, sequential, clustered, sequential_audit, clustered_audit, paths


def test_protocol_report_handles_aime_index_zero_and_requires_complete_pass_k(tmp_path):
    protocol, sequential, clustered, sequential_audit, clustered_audit, paths = (
        _protocol_report_fixture(tmp_path)
    )
    report = build_three_group_report(
        evaluation_paths=paths,
        evaluation_exp_ids=None,
        sequential_hierarchy=sequential,
        clustered_hierarchy=clustered,
        experiment_protocol_path=protocol,
        sequential_audit=sequential_audit,
        clustered_audit=clustered_audit,
    )
    assert [row["task_id"] for row in report["per_task"]] == ["AIME24:0", "AIME24:1"]
    assert report["integrity"]["runtime_parameter_verification"]["status"] == "verified"
    assert report["groups"]["clustered"]["injected_token_source"] == "evaluation_metadata"

    broken_rows = json.loads(paths["clustered"].read_text(encoding="utf-8"))
    paths["clustered"].write_text(json.dumps(broken_rows[:-1]), encoding="utf-8")
    with pytest.raises(ValueError, match="Incomplete pass-k"):
        build_three_group_report(
            evaluation_paths=paths,
            evaluation_exp_ids=None,
            sequential_hierarchy=sequential,
            clustered_hierarchy=clustered,
            experiment_protocol_path=protocol,
            sequential_audit=sequential_audit,
            clustered_audit=clustered_audit,
        )


def test_protocol_report_rejects_missing_runtime_metadata(tmp_path):
    protocol, sequential, clustered, sequential_audit, clustered_audit, paths = (
        _protocol_report_fixture(tmp_path)
    )
    rows = json.loads(paths["sequential"].read_text(encoding="utf-8"))
    rows[0]["meta"].pop("experiment_protocol_sha256")
    paths["sequential"].write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(ValueError, match="lacks required protocol metadata"):
        build_three_group_report(
            evaluation_paths=paths,
            evaluation_exp_ids=None,
            sequential_hierarchy=sequential,
            clustered_hierarchy=clustered,
            experiment_protocol_path=protocol,
            sequential_audit=sequential_audit,
            clustered_audit=clustered_audit,
        )


def test_protocol_report_requires_untampered_cluster_audits(tmp_path):
    protocol, sequential, clustered, sequential_audit, clustered_audit, paths = (
        _protocol_report_fixture(tmp_path)
    )
    clustered_audit.write_text('{"tampered": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="cluster audit differs"):
        build_three_group_report(
            evaluation_paths=paths,
            evaluation_exp_ids=None,
            sequential_hierarchy=sequential,
            clustered_hierarchy=clustered,
            experiment_protocol_path=protocol,
            sequential_audit=sequential_audit,
            clustered_audit=clustered_audit,
        )


def test_db_result_loader_preserves_runtime_meta(monkeypatch):
    sample = SimpleNamespace(
        meta={"experiment_protocol_sha256": "signed", "trial_index": 0},
        model_dump=lambda **kwargs: {
            "dataset": "AIME24",
            "dataset_index": 0,
            "stage": "judged",
            "reward": 1.0,
        },
    )

    class Result:
        def all(self):
            return [sample]

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def exec(self, statement):
            return Result()

    monkeypatch.setattr(
        hierarchical_ablation.SQLModelUtils,
        "create_session",
        lambda: Session(),
    )
    rows = hierarchical_ablation._load_result_rows(None, "exp")
    assert rows[0]["meta"]["experiment_protocol_sha256"] == "signed"
    assert hierarchical_ablation._row_task_id(rows[0]) == "AIME24:0"


def test_hierarchy_metrics_excludes_inactive_and_needs_review_records(tmp_path):
    hierarchy = tmp_path / "active_only.json"
    hierarchy.write_text(
        json.dumps(
            {
                "l0_experiences": [
                    _record("active lesson", 1),
                    {**_record("inactive lesson", 2), "lifecycle_status": "inactive"},
                ],
                "l1_experiences": [
                    {
                        "id": "stale-l1",
                        "level": "L1",
                        "content": "stale",
                        "lifecycle_status": "needs_review",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    metrics = hierarchy_metrics(hierarchy)
    assert metrics["counts"] == {"L0": 1, "L1": 0, "L2": 0}
    assert metrics["final_prompt_token_count"] > 0


def test_run_eval_protocol_guard_fails_before_inventory_or_runner(monkeypatch, tmp_path):
    base = ConfigLoader.load_eval_config("math/math_AIME24")
    config = base.model_copy(deep=True)
    condition = "clustered"
    protocol = sign_experiment_protocol(
        {
            "status": "ready",
            "conditions": ["no_experience", "sequential", "clustered"],
            "training": {
                "validation_mode": "strict_practice_manifest",
                "dataset": "DAPO-v3-test",
                "manifest_path": "manifest.json",
                "split_name": "training",
                "record_count": 1,
                "snapshot_sha256": "train-hash",
            },
            "evaluation": {
                "dataset": "AIME24",
                "eval_config_name": "math/math_AIME24",
                "resolved_config_sha256": config_sha256(base),
                "task_order_sha256": canonical_sha256(["AIME24:0"]),
                "snapshot_sha256": "eval-hash",
            },
            "shared_parameters": {
                "pass_k": config.pass_k,
                "concurrency": config.concurrency,
                "judge_concurrency": config.judge_concurrency,
                "model_config_sha256": config_sha256(config.agent.model),
            },
            "condition_configs": {
                condition: {
                    "agent_config_sha256": config_sha256(config.agent),
                    "prompt_sha256": "prompt",
                    "declared_injected_token_count": 9,
                    "injected_tokenizer": "cl100k_base",
                    "expected_exp_id": "signed-exp",
                }
            },
        }
    )
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    args = Namespace(
        experiment_protocol=str(protocol_path),
        config_name="math/math_AIME24",
        experience_condition=condition,
        train_dataset="DAPO-v3-test",
        injected_token_count=9,
        injected_tokenizer="cl100k_base",
        exp_id="signed-exp",
    )
    called = {"inventory": False}

    def fail_manifest(**kwargs):
        raise ValueError("frozen snapshot mismatch")

    monkeypatch.setattr(run_eval, "validate_practice_dataset_manifest", fail_manifest)
    monkeypatch.setattr(
        run_eval,
        "validate_evaluation_inventory",
        lambda *args, **kwargs: called.update(inventory=True),
    )
    with pytest.raises(ValueError, match="frozen snapshot mismatch"):
        run_eval.validate_experiment_protocol_before_runner(
            args,
            base_config=base,
            config=config,
        )
    assert called["inventory"] is False


def test_run_eval_rejects_invalid_existing_trial_before_runner(monkeypatch, tmp_path):
    base = ConfigLoader.load_eval_config("math/math_AIME24")
    config = base.model_copy(deep=True)
    condition = "clustered"
    question = "frozen question"
    task_order = ["AIME24:0"]
    condition_contract = {
        "agent_config_sha256": config_sha256(config.agent),
        "prompt_sha256": "prompt-hash",
        "declared_injected_token_count": 9,
        "injected_tokenizer": "cl100k_base",
        "expected_exp_id": "signed-existing-exp",
    }
    protocol = sign_experiment_protocol(
        {
            "status": "ready",
            "conditions": ["no_experience", "sequential", "clustered"],
            "training": {
                "validation_mode": "strict_practice_manifest",
                "dataset": "DAPO-v3-test",
                "manifest_path": "manifest.json",
                "split_name": "training",
                "record_count": 1,
                "snapshot_sha256": "train-hash",
            },
            "evaluation": {
                "dataset": "AIME24",
                "eval_config_name": "math/math_AIME24",
                "resolved_config_sha256": config_sha256(base),
                "task_order": task_order,
                "task_order_sha256": canonical_sha256(task_order),
                "snapshot_sha256": "eval-hash",
                "tasks": [
                    {
                        "namespaced_task_id": "AIME24:0",
                        "question_sha256": hashlib.sha256(question.encode()).hexdigest(),
                    }
                ],
            },
            "shared_parameters": {
                "pass_k": config.pass_k,
                "concurrency": config.concurrency,
                "judge_concurrency": config.judge_concurrency,
                "model_config_sha256": config_sha256(config.agent.model),
            },
            "condition_configs": {condition: condition_contract},
        }
    )
    protocol_path = tmp_path / "existing_protocol.json"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    args = Namespace(
        experiment_protocol=str(protocol_path),
        config_name="math/math_AIME24",
        experience_condition=condition,
        train_dataset="DAPO-v3-test",
        injected_token_count=9,
        injected_tokenizer="cl100k_base",
        exp_id="signed-existing-exp",
    )
    expected_meta = run_eval._protocol_runtime_metadata(
        config,
        protocol=protocol,
        condition=condition,
        injected_token_count=9,
        injected_tokenizer="cl100k_base",
    )
    existing = SimpleNamespace(
        dataset="AIME24",
        dataset_index=0,
        raw_question=question,
        stage="init",
        meta={**expected_meta, "trial_index": config.pass_k},
    )

    class Result:
        def all(self):
            return [existing]

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def exec(self, statement):
            return Result()

    monkeypatch.setattr(
        run_eval,
        "validate_practice_dataset_manifest",
        lambda **kwargs: {
            "practice_snapshot_sha256": "train-hash",
            "evaluation_snapshot_sha256": "eval-hash",
        },
    )
    monkeypatch.setattr(run_eval, "validate_evaluation_inventory", lambda *args, **kwargs: {})
    monkeypatch.setattr(run_eval.SQLModelUtils, "configure", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_eval.SQLModelUtils, "create_session", lambda: Session())

    with pytest.raises(ValueError, match="invalid trial_index"):
        run_eval.validate_experiment_protocol_before_runner(
            args,
            base_config=base,
            config=config,
        )
