#!/usr/bin/env python3
"""Prepare the unified no-experience/sequential/clustered SkillsBench experiment."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

from utu.config import ConfigLoader
from utu.practice.hierarchical_ablation import prepare_ablation_seed, source_l0_fingerprint
from utu.practice.hierarchical_experience_manager import HierarchicalExperienceManager
from utu.practice.training_free_grpo import TrainingFreeGRPO
from utu.skillsbench_data import canonical_sha256, load_task_split_manifest
from utu.utils import DIR_ROOT, TokenUtils, redact_sensitive_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-name", required=True)
    parser.add_argument("--source-experiences", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--eval-config",
        default="skillsbench/skillsbench_paper_baseline_eval",
        help="One common evaluation config used by all three conditions.",
    )
    parser.add_argument("--plan-only", action="store_true", help="Validate and write a plan without LLM aggregation.")
    return parser.parse_args()


def _agent_yaml(manager: HierarchicalExperienceManager, config, suffix: str, run_name: str) -> str:
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


async def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sequential_path = output_dir / "sequential.json"
    clustered_path = output_dir / "clustered.json"
    sequential_audit = output_dir / "sequential.clusters.jsonl"
    clustered_audit = output_dir / "clustered.clusters.jsonl"
    plan_path = output_dir / "experiment_plan.json"
    targets = [plan_path]
    if not args.plan_only:
        targets += [sequential_path, clustered_path, sequential_audit, clustered_audit]
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        raise FileExistsError(f"Refusing to overwrite existing ablation artifacts: {existing}")

    config = ConfigLoader.load_training_free_grpo_config(args.config_name)
    base_hierarchy = config.practice.hierarchical_learning
    skillsbench = config.evaluation.skillsbench
    if not skillsbench.task_split_manifest_path or not skillsbench.task_split_name:
        raise ValueError("Practice evaluation config must declare a versioned SkillsBench split manifest")
    manifest = load_task_split_manifest(skillsbench.task_split_manifest_path)
    split = manifest["splits"][skillsbench.task_split_name]
    source_fingerprint = source_l0_fingerprint(args.source_experiences)
    shared_parameters = {
        "model": redact_sensitive_data(config.evaluation.agent.model.model_dump(mode="json")),
        "evaluation_dataset": config.evaluation.data.dataset,
        "pass_k": config.evaluation.pass_k,
        "concurrency": config.evaluation.concurrency,
        "task_order": split["eval_task_ids"],
        "task_order_sha256": canonical_sha256(split["eval_task_ids"]),
        "random_seed": base_hierarchy.random_seed,
        "aggregation_temperature": 0.0,
    }
    plan = {
        "schema_version": "three-condition-v1",
        "conditions": ["no_experience", "sequential", "clustered"],
        "source_l0": source_fingerprint,
        "dataset": manifest["dataset"],
        "split_name": skillsbench.task_split_name,
        "split_sha256": split["split_sha256"],
        "train_task_ids": split["train_task_ids"],
        "eval_task_ids": split["eval_task_ids"],
        "shared_parameters": shared_parameters,
        "shared_parameters_sha256": canonical_sha256(shared_parameters),
        "eval_config": args.eval_config,
        "status": "plan_only" if args.plan_only else "aggregation_prepared",
    }
    if args.plan_only:
        with plan_path.open("x", encoding="utf-8") as file:
            json.dump(plan, file, ensure_ascii=False, indent=2)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return

    if base_hierarchy.aggregation_temperature != 0.0:
        raise ValueError("Unified experiment requires aggregation_temperature=0.0")
    if base_hierarchy.similarity_thresholds_provisional:
        raise ValueError(
            "Clustered experiment is blocked until training-only threshold calibration is reviewed; "
            "set similarity_thresholds_provisional=false only after accepting a reviewed training-only report"
        )
    sequential_seed = prepare_ablation_seed(args.source_experiences, sequential_path)
    clustered_seed = prepare_ablation_seed(args.source_experiences, clustered_path)
    if sequential_seed["source_l0_sha256"] != clustered_seed["source_l0_sha256"]:
        raise AssertionError("Ablation seeds do not share the exact same L0 snapshot")
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

    run_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", output_dir.name)
    agents = {
        "sequential": _agent_yaml(sequential_manager, config, "sequential", run_name),
        "clustered": _agent_yaml(clustered_manager, config, "clustered", run_name),
    }
    base_instruction_tokens = TokenUtils.count_tokens(config.evaluation.agent.agent.instructions or "")
    injected_tokens = {"no_experience": 0}
    for condition in ("sequential", "clustered"):
        learned_agent = ConfigLoader.load_agent_config(agents[condition])
        learned_tokens = TokenUtils.count_tokens(learned_agent.agent.instructions or "")
        injected_tokens[condition] = max(0, learned_tokens - base_instruction_tokens)
    eval_dataset = config.evaluation.data.dataset
    train_dataset = config.data.practice_dataset_name
    base_command = [
        "python", "scripts/run_eval.py", "--config_name", args.eval_config,
        "--dataset", eval_dataset, "--train_dataset", train_dataset,
    ]
    plan["generated_agent_configs"] = agents
    plan["evaluation_commands"] = {
        "no_experience": base_command + [
            "--exp_id", f"{config.exp_id}_no_experience_{run_name}",
            "--experience_condition", "no_experience", "--injected_token_count", "0",
        ],
        "sequential": base_command + [
            "--exp_id", f"{config.exp_id}_sequential_{run_name}",
            "--experience_condition", "sequential", "--agent_config", agents["sequential"],
            "--injected_token_count", str(injected_tokens["sequential"]),
        ],
        "clustered": base_command + [
            "--exp_id", f"{config.exp_id}_clustered_{run_name}",
            "--experience_condition", "clustered", "--agent_config", agents["clustered"],
            "--injected_token_count", str(injected_tokens["clustered"]),
        ],
    }
    plan["declared_injected_token_count"] = injected_tokens
    plan["injected_tokenizer"] = "cl100k_base"
    plan["evaluation_order"] = ["no_experience", "sequential", "clustered"]
    with plan_path.open("x", encoding="utf-8") as file:
        json.dump(plan, file, ensure_ascii=False, indent=2)
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
