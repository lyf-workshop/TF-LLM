#!/usr/bin/env python3
"""Prepare one frozen no-experience/sequential/clustered experiment."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from utu.config import ConfigLoader
from utu.practice.dataset_manifest_guard import (
    validate_hierarchy_snapshot_sources,
    validate_practice_dataset_manifest,
)
from utu.practice.hierarchical_ablation import (
    config_sha256,
    load_evaluation_inventory,
    prepare_ablation_seed,
    sign_experiment_protocol,
    source_l0_fingerprint,
)
from utu.practice.hierarchical_experience_manager import HierarchicalExperienceManager
from utu.practice.training_free_grpo import TrainingFreeGRPO
from utu.skillsbench_data import (
    assert_datasets_disjoint,
    canonical_sha256,
    load_task_split_manifest,
)
from utu.utils import DIR_ROOT, TokenUtils, redact_sensitive_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-name", required=True)
    parser.add_argument("--source-experiences", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--eval-config",
        default=None,
        help=(
            "One common evaluation config. Defaults to the paper SkillsBench config "
            "for SkillsBench and math/math_AIME24 for strict DAPO/AIME configs."
        ),
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Write a non-executable plan without DB/LLM work.",
    )
    return parser.parse_args()


def _resolved_path(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = DIR_ROOT / candidate
    return candidate.resolve()


def _write_agent_yaml(
    manager: HierarchicalExperienceManager | None,
    config,
    suffix: str,
    run_name: str,
) -> str:
    copied = config.model_copy(deep=True)
    copied.exp_id = f"{config.exp_id}_{suffix}_{run_name}"
    copied.evaluation.exp_id = copied.exp_id
    target = DIR_ROOT / "configs" / "agents" / "practice" / f"{copied.exp_id}_agent.yaml"
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite generated agent config: {target}")
    runner = TrainingFreeGRPO(copied)
    runner.hierarchical_experience_manager = manager
    runner.original_temperature = copied.evaluation.agent.model.model_settings.temperature
    generated = Path(runner._create_agent_config_with_experiences({}))
    return generated.relative_to(DIR_ROOT / "configs" / "agents").with_suffix("").as_posix()


def _load_manifest(path_value: str) -> tuple[Path, dict[str, Any]]:
    path = _resolved_path(path_value)
    if not path.exists():
        raise ValueError(f"Required dataset manifest does not exist: {path}")
    return path, load_task_split_manifest(path)


def _static_training_contract(config) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify manifest signatures without reading or modifying the database."""

    if config.data.require_practice_manifest:
        manifest_path, manifest = _load_manifest(config.data.practice_manifest_path)
        split_name = config.data.practice_manifest_split
        if manifest.get("schema_version") != 3:
            raise ValueError("Strict DAPO/AIME ablation requires a schema_version=3 manifest")
        if manifest.get("target_dataset") != config.data.practice_dataset_name:
            raise ValueError("Practice dataset differs from strict manifest target_dataset")
        split = manifest["splits"].get(split_name)
        if not isinstance(split, dict):
            raise ValueError(f"Strict practice manifest has no split {split_name!r}")
        tasks = manifest.get("tasks") or []
        task_ids = list(split.get("train_task_ids") or [])
        namespace = manifest.get("dataset", {}).get("namespace")
        if not namespace or task_ids != [str(task.get("task_id")) for task in tasks]:
            raise ValueError("Strict practice split does not match its ordered task inventory")
        expected_count = config.data.practice_manifest_expected_records
        if len(task_ids) != expected_count:
            raise ValueError("Strict practice manifest record count differs from configuration")
        exclusion = manifest.get("evaluation_exclusion") or {}
        eval_dataset = config.evaluation.data.dataset
        if exclusion.get("dataset") != eval_dataset:
            raise ValueError("Strict manifest evaluation exclusion differs from configured evaluation dataset")
        namespaced_train_ids = [f"{namespace}:{task_id}" for task_id in task_ids]
        training = {
            "validation_mode": "strict_practice_manifest",
            "dataset": config.data.practice_dataset_name,
            "namespace": namespace,
            "dataset_version": manifest["dataset"]["version"],
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest["manifest_sha256"],
            "split_name": split_name,
            "split_sha256": split["split_sha256"],
            "record_count": expected_count,
            "task_ids": namespaced_train_ids,
            "task_ids_sha256": canonical_sha256(namespaced_train_ids),
            "snapshot_sha256": manifest["target_dataset_sha256"],
            "database_validation": "pending",
        }
        evaluation = {
            "dataset": eval_dataset,
            "record_count": exclusion.get("record_count"),
            "snapshot_sha256": exclusion.get("snapshot_sha256"),
            "snapshot_algorithm": "dapo_manifest_evaluation_exclusion_v1",
            "inventory_availability": "requires_execute_database_validation",
            "tasks": [],
            "inventory_sha256": None,
            "task_order": [],
            "task_order_sha256": None,
            "result_task_order": [],
            "result_task_order_sha256": None,
            "metadata_defaults": {"domain": "mathematics", "task_family": None},
        }
        return training, evaluation

    skillsbench = config.evaluation.skillsbench
    if not skillsbench.task_split_manifest_path or not skillsbench.task_split_name:
        raise ValueError(
            "Non-strict ablation configs must declare a versioned SkillsBench split manifest"
        )
    manifest_path, manifest = _load_manifest(skillsbench.task_split_manifest_path)
    split = manifest["splits"][skillsbench.task_split_name]
    task_by_id = {str(task["task_id"]): task for task in manifest["tasks"]}
    eval_dataset = config.evaluation.data.dataset
    eval_ids = list(split["eval_task_ids"])
    tasks = []
    for task_id in eval_ids:
        item = task_by_id[task_id]
        tasks.append(
            {
                "task_id": task_id,
                "namespaced_task_id": f"{eval_dataset}:{task_id}",
                "dataset_index": None,
                "question_sha256": item.get("question_sha256"),
                "domain": item.get("domain"),
                "task_family": item.get("task_family"),
            }
        )
    training = {
        "validation_mode": "skillsbench_split_manifest",
        "dataset": config.data.practice_dataset_name,
        "namespace": manifest["dataset"].get("namespace") or manifest["dataset"]["name"],
        "dataset_version": manifest["dataset"].get("version"),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest.get("manifest_sha256"),
        "split_name": skillsbench.task_split_name,
        "split_sha256": split["split_sha256"],
        "record_count": len(split["train_task_ids"]),
        "task_ids": list(split["train_task_ids"]),
        "task_ids_sha256": canonical_sha256(split["train_task_ids"]),
        "task_ids_set_sha256": canonical_sha256(sorted(split["train_task_ids"])),
        "snapshot_sha256": manifest["dataset"].get("inventory_sha256"),
        "database_validation": "pending",
    }
    task_order = [task["namespaced_task_id"] for task in tasks]
    evaluation = {
        "dataset": eval_dataset,
        "record_count": len(tasks),
        "snapshot_sha256": None,
        "snapshot_algorithm": "protocol_inventory_v1",
        "inventory_availability": "manifest_order_only",
        "tasks": tasks,
        "inventory_sha256": canonical_sha256(tasks),
        "task_order": task_order,
        "task_order_sha256": canonical_sha256(task_order),
        "result_task_order": eval_ids,
        "result_task_order_sha256": canonical_sha256(eval_ids),
        "metadata_defaults": {"domain": None, "task_family": None},
    }
    return training, evaluation


def _verified_evaluation_inventory(
    config,
    training: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate DB snapshots and construct the exact order shared by all groups."""

    dataset = config.evaluation.data.dataset
    db_url = config.evaluation.db_url
    if training["validation_mode"] == "strict_practice_manifest":
        evidence = validate_practice_dataset_manifest(
            practice_dataset=training["dataset"],
            manifest_path=training["manifest_path"],
            split_name=training["split_name"],
            expected_record_count=training["record_count"],
            evaluation_dataset=dataset,
            db_url=db_url,
        )
        inventory = load_evaluation_inventory(dataset, db_url=db_url, default_domain="mathematics")
        if inventory["record_count"] != evidence["evaluation_record_count"]:
            raise ValueError("Evaluation inventory count differs from strict manifest evidence")
        inventory.update(
            snapshot_sha256=evidence["evaluation_snapshot_sha256"],
            snapshot_algorithm="dapo_manifest_evaluation_exclusion_v1",
            inventory_availability="verified_from_database",
            metadata_defaults={"domain": "mathematics", "task_family": None},
        )
        training = {
            **training,
            "snapshot_sha256": evidence["practice_snapshot_sha256"],
            "database_validation": "verified",
            "database_evidence": evidence,
        }
        return training, inventory

    evidence = assert_datasets_disjoint(
        training["dataset"],
        dataset,
        db_url=db_url,
        split_manifest_path=training["manifest_path"],
        split_name=training["split_name"],
    )
    actual = load_evaluation_inventory(dataset, db_url=db_url)
    manifest = load_task_split_manifest(training["manifest_path"])
    expected_ids = list(manifest["splits"][training["split_name"]]["eval_task_ids"])
    actual_by_result_id = {task["task_id"]: task for task in actual["tasks"]}
    if set(actual_by_result_id) != set(expected_ids):
        raise ValueError("SkillsBench evaluation DB inventory differs from manifest split")
    tasks = [actual_by_result_id[task_id] for task_id in expected_ids]
    task_order = [task["namespaced_task_id"] for task in tasks]
    actual.update(
        tasks=tasks,
        inventory_sha256=canonical_sha256(tasks),
        task_order=task_order,
        task_order_sha256=canonical_sha256(task_order),
        result_task_order=expected_ids,
        result_task_order_sha256=canonical_sha256(expected_ids),
        snapshot_sha256=canonical_sha256(tasks),
        snapshot_algorithm="protocol_inventory_v1",
        inventory_availability="verified_from_database",
        metadata_defaults={"domain": None, "task_family": None},
    )
    training = {**training, "database_validation": "verified", "database_evidence": evidence}
    return training, actual


def _agent_without_prompt(agent) -> dict[str, Any]:
    payload = agent.model_dump(mode="json")
    if isinstance(payload.get("agent"), dict):
        payload["agent"] = {**payload["agent"], "instructions": None}
    return payload


def _condition_agent_contracts(agents: dict[str, str], config) -> dict[str, Any]:
    base_agent = config.evaluation.agent
    baseline = ConfigLoader.load_agent_config(agents["no_experience"])
    if config_sha256(baseline) != config_sha256(base_agent):
        raise ValueError("no_experience agent is not the exact practice base agent")
    common_without_prompt = canonical_sha256(_agent_without_prompt(baseline))
    contracts = {}
    for condition, path in agents.items():
        loaded = ConfigLoader.load_agent_config(path)
        if canonical_sha256(_agent_without_prompt(loaded)) != common_without_prompt:
            raise ValueError(f"{condition} agent changed settings outside the experience prompt")
        instructions = loaded.agent.instructions or ""
        agent_file = DIR_ROOT / "configs" / "agents" / f"{path}.yaml"
        contracts[condition] = {
            "agent_config": path,
            "agent_config_sha256": config_sha256(loaded),
            "agent_file_sha256": hashlib.sha256(agent_file.read_bytes()).hexdigest(),
            "prompt_sha256": hashlib.sha256(instructions.encode("utf-8")).hexdigest(),
        }
    contracts["no_experience"]["contains_experience_injection"] = False
    return contracts


async def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sequential_path = output_dir / "sequential.json"
    clustered_path = output_dir / "clustered.json"
    sequential_audit = output_dir / "sequential.clusters.jsonl"
    clustered_audit = output_dir / "clustered.clusters.jsonl"
    plan_path = output_dir / "experiment_plan.json"
    protocol_path = output_dir / "experiment_protocol.json"
    run_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", output_dir.name)
    targets = [plan_path, protocol_path]
    if not args.plan_only:
        targets += [sequential_path, clustered_path, sequential_audit, clustered_audit]
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        raise FileExistsError(f"Refusing to overwrite existing ablation artifacts: {existing}")

    config = ConfigLoader.load_training_free_grpo_config(args.config_name)
    base_hierarchy = config.practice.hierarchical_learning
    training, evaluation = _static_training_contract(config)
    if training["validation_mode"] == "strict_practice_manifest":
        with Path(args.source_experiences).open("r", encoding="utf-8") as file:
            source_payload = json.load(file)
        training["hierarchy_source_validation"] = validate_hierarchy_snapshot_sources(
            source_payload,
            manifest_path=training["manifest_path"],
            practice_dataset=training["dataset"],
        )
    inferred_eval = (
        "math/math_AIME24"
        if training["validation_mode"] == "strict_practice_manifest"
        else "skillsbench/skillsbench_paper_baseline_eval"
    )
    eval_config_name = args.eval_config or inferred_eval
    resolved_eval_config = ConfigLoader.load_eval_config(eval_config_name)
    if resolved_eval_config.data.dataset != evaluation["dataset"]:
        raise ValueError(
            f"Evaluation config dataset {resolved_eval_config.data.dataset!r} differs from "
            f"frozen dataset {evaluation['dataset']!r}"
        )
    evaluation["eval_config_name"] = eval_config_name
    evaluation["resolved_config_sha256"] = config_sha256(resolved_eval_config)

    source_fingerprint = source_l0_fingerprint(args.source_experiences)
    shared_parameters = {
        "model": redact_sensitive_data(config.evaluation.agent.model.model_dump(mode="json")),
        "model_config_sha256": config_sha256(config.evaluation.agent.model),
        "base_agent_sha256": config_sha256(config.evaluation.agent),
        "evaluation_config": eval_config_name,
        "evaluation_config_sha256": evaluation["resolved_config_sha256"],
        "evaluation_dataset": evaluation["dataset"],
        "pass_k": resolved_eval_config.pass_k,
        "concurrency": resolved_eval_config.concurrency,
        "judge_concurrency": resolved_eval_config.judge_concurrency,
        "task_order": evaluation["task_order"] or None,
        "task_order_sha256": evaluation["task_order_sha256"],
        "random_seed": base_hierarchy.random_seed,
        "aggregation_temperature": 0.0,
    }
    protocol_payload = {
        "schema_version": "three-condition-v2",
        "status": "plan_only_unverified" if args.plan_only else "ready",
        "conditions": ["no_experience", "sequential", "clustered"],
        "source_l0": source_fingerprint,
        "training": training,
        "evaluation": evaluation,
        "shared_parameters": shared_parameters,
        "shared_parameters_sha256": canonical_sha256(shared_parameters),
        "condition_configs": {},
    }
    if args.plan_only:
        protocol = sign_experiment_protocol(protocol_payload)
        protocol_path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")
        planned_exp_ids = {
            condition: f"{config.exp_id}_{condition}_{run_name}"
            for condition in ("no_experience", "sequential", "clustered")
        }
        report_command = [
            "python",
            "scripts/experiments/report_hierarchical_ablation.py",
            "--experiment-protocol",
            str(protocol_path),
            "--sequential-hierarchy",
            str(sequential_path),
            "--clustered-hierarchy",
            str(clustered_path),
            "--sequential-audit",
            str(sequential_audit),
            "--clustered-audit",
            str(clustered_audit),
            "--no-experience-exp-id",
            planned_exp_ids["no_experience"],
            "--sequential-exp-id",
            planned_exp_ids["sequential"],
            "--clustered-exp-id",
            planned_exp_ids["clustered"],
            "--output",
            str(output_dir / "three_condition_report.json"),
        ]
        plan = {
            "schema_version": "three-condition-v2",
            "conditions": protocol["conditions"],
            "source_l0": source_fingerprint,
            "training": training,
            "evaluation": evaluation,
            "eval_task_ids": evaluation["result_task_order"],
            "shared_parameters": shared_parameters,
            "experiment_protocol": str(protocol_path),
            "experiment_protocol_sha256": protocol["protocol_sha256"],
            "report_command": report_command,
            "report_command_status": "planned; requires execute preparation and completed evaluations",
            "status": "plan_only",
        }
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return

    # Full snapshot/leakage validation precedes manager construction or LLM calls.
    training, evaluation = _verified_evaluation_inventory(config, training)
    if base_hierarchy.aggregation_temperature != 0.0:
        raise ValueError("Unified experiment requires aggregation_temperature=0.0")
    provisional_levels = [
        level
        for level, is_provisional in (
            ("L0", base_hierarchy.l0_similarity_threshold_provisional),
            ("L1", base_hierarchy.l1_similarity_threshold_provisional),
        )
        if is_provisional
    ]
    if provisional_levels:
        raise ValueError(
            "Clustered experiment is blocked until training-only threshold calibration is reviewed "
            f"for: {', '.join(provisional_levels)}; clear each layer's provisional flag only after "
            "accepting its reviewed training-only report"
        )

    sequential_seed = prepare_ablation_seed(args.source_experiences, sequential_path)
    clustered_seed = prepare_ablation_seed(args.source_experiences, clustered_path)
    if sequential_seed["source_l0_sha256"] != clustered_seed["source_l0_sha256"]:
        raise AssertionError("Ablation seeds do not share the exact same L0 snapshot")
    if sequential_seed["source_l0_sha256"] != source_fingerprint["source_l0_sha256"]:
        raise AssertionError("Ablation seed differs from the validated source L0 snapshot")
    sequential_config = base_hierarchy.model_copy(
        update={
            "clustering_enabled": False,
            "aggregation_temperature": 0.0,
            "experience_save_path": str(sequential_path),
            "clustering_audit_path": str(sequential_audit),
        },
        deep=True,
    )
    clustered_config = base_hierarchy.model_copy(
        update={
            "clustering_enabled": True,
            "aggregation_temperature": 0.0,
            "experience_save_path": str(clustered_path),
            "clustering_audit_path": str(clustered_audit),
        },
        deep=True,
    )
    common = {
        "config": config.evaluation.agent,
        "agent_objective": config.practice.agent_objective,
        "learning_objective": config.practice.learning_objective,
    }
    sequential_manager = HierarchicalExperienceManager(hierarchical_config=sequential_config, **common)
    clustered_manager = HierarchicalExperienceManager(hierarchical_config=clustered_config, **common)
    await sequential_manager.aggregate_epoch(epoch=0)
    await clustered_manager.aggregate_epoch(epoch=0)

    agents = {
        "no_experience": _write_agent_yaml(None, config, "no_experience", run_name),
        "sequential": _write_agent_yaml(sequential_manager, config, "sequential", run_name),
        "clustered": _write_agent_yaml(clustered_manager, config, "clustered", run_name),
    }
    condition_configs = _condition_agent_contracts(agents, config)
    base_instruction_tokens = TokenUtils.count_tokens(config.evaluation.agent.agent.instructions or "")
    injected_tokens = {"no_experience": 0}
    for condition in ("sequential", "clustered"):
        learned_agent = ConfigLoader.load_agent_config(agents[condition])
        learned_tokens = TokenUtils.count_tokens(learned_agent.agent.instructions or "")
        injected_tokens[condition] = max(0, learned_tokens - base_instruction_tokens)
    for condition in condition_configs:
        condition_configs[condition]["declared_injected_token_count"] = injected_tokens[condition]
        condition_configs[condition]["injected_tokenizer"] = "cl100k_base"
        condition_configs[condition]["expected_exp_id"] = (
            f"{config.exp_id}_{condition}_{run_name}"
        )
    condition_configs["sequential"]["hierarchy_file_sha256"] = hashlib.sha256(
        sequential_path.read_bytes()
    ).hexdigest()
    condition_configs["clustered"]["hierarchy_file_sha256"] = hashlib.sha256(
        clustered_path.read_bytes()
    ).hexdigest()
    for condition, audit_path in (
        ("sequential", sequential_audit),
        ("clustered", clustered_audit),
    ):
        if not audit_path.is_file():
            raise ValueError(f"{condition} aggregation did not produce its required cluster audit")
        condition_configs[condition]["audit_file_sha256"] = hashlib.sha256(
            audit_path.read_bytes()
        ).hexdigest()

    shared_parameters["task_order"] = evaluation["task_order"]
    shared_parameters["task_order_sha256"] = evaluation["task_order_sha256"]
    protocol_payload.update(
        status="ready",
        training=training,
        evaluation={
            **evaluation,
            "eval_config_name": eval_config_name,
            "resolved_config_sha256": config_sha256(resolved_eval_config),
        },
        shared_parameters=shared_parameters,
        shared_parameters_sha256=canonical_sha256(shared_parameters),
        condition_configs=condition_configs,
    )
    protocol = sign_experiment_protocol(protocol_payload)
    protocol_path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")

    model_name = str(config.evaluation.agent.model.model_provider.model)
    base_command = [
        "python",
        "scripts/run_eval.py",
        "--config_name",
        eval_config_name,
        "--dataset",
        evaluation["dataset"],
        "--train_dataset",
        training["dataset"],
        "--agent_model",
        model_name,
        "--experiment_protocol",
        str(protocol_path),
    ]
    evaluation_commands = {}
    for condition in ("no_experience", "sequential", "clustered"):
        evaluation_commands[condition] = base_command + [
            "--exp_id",
            condition_configs[condition]["expected_exp_id"],
            "--experience_condition",
            condition,
            "--agent_config",
            agents[condition],
            "--injected_token_count",
            str(injected_tokens[condition]),
        ]
    report_command = [
        "python",
        "scripts/experiments/report_hierarchical_ablation.py",
        "--experiment-protocol",
        str(protocol_path),
        "--sequential-hierarchy",
        str(sequential_path),
        "--clustered-hierarchy",
        str(clustered_path),
        "--sequential-audit",
        str(sequential_audit),
        "--clustered-audit",
        str(clustered_audit),
        "--no-experience-exp-id",
        condition_configs["no_experience"]["expected_exp_id"],
        "--sequential-exp-id",
        condition_configs["sequential"]["expected_exp_id"],
        "--clustered-exp-id",
        condition_configs["clustered"]["expected_exp_id"],
        "--output",
        str(output_dir / "three_condition_report.json"),
    ]
    plan = {
        "schema_version": "three-condition-v2",
        "conditions": protocol["conditions"],
        "source_l0": source_fingerprint,
        "training": training,
        "evaluation": protocol["evaluation"],
        "eval_task_ids": evaluation["result_task_order"],
        "shared_parameters": shared_parameters,
        "shared_parameters_sha256": protocol["shared_parameters_sha256"],
        "eval_config": eval_config_name,
        "generated_agent_configs": agents,
        "condition_configs": condition_configs,
        "evaluation_commands": evaluation_commands,
        "report_command": report_command,
        "declared_injected_token_count": injected_tokens,
        "injected_tokenizer": "cl100k_base",
        "evaluation_order": ["no_experience", "sequential", "clustered"],
        "experiment_protocol": str(protocol_path),
        "experiment_protocol_sha256": protocol["protocol_sha256"],
        "status": "aggregation_prepared",
    }
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
