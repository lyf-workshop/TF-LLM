import argparse
import asyncio
import hashlib
import json

from sqlmodel import select

from utu.config import ConfigLoader, EvalConfig
from utu.db import EvaluationSample
from utu.eval import BaseBenchmark
from utu.practice.dataset_manifest_guard import validate_practice_dataset_manifest
from utu.practice.hierarchical_ablation import (
    config_sha256,
    load_experiment_protocol,
    validate_evaluation_inventory,
)
from utu.skillsbench_data import assert_datasets_disjoint
from utu.utils import SQLModelUtils, redact_sensitive_data


def get_eval_config(args: argparse.Namespace, config: EvalConfig | None = None) -> EvalConfig:
    config = config or ConfigLoader.load_eval_config(args.config_name)
    if args.agent_config:
        config.agent = ConfigLoader.load_agent_config(args.agent_config)
    if args.exp_id:
        config.exp_id = args.exp_id
    if args.agent_model:
        config.agent.model.model_provider.model = args.agent_model
    if args.dataset:
        config.data.dataset = args.dataset
    if args.pass_k is not None:
        config.pass_k = args.pass_k
    if args.concurrency is not None:
        config.concurrency = args.concurrency
    if args.judge_concurrency is not None:
        config.judge_concurrency = args.judge_concurrency
    if args.korgym_timeout_per_game is not None:
        config.korgym.timeout_per_game = args.korgym_timeout_per_game
    if args.allow_legacy_cache_reuse:
        config.allow_legacy_cache_reuse = True
    if args.experience_condition:
        config.skillsbench.experience_condition = args.experience_condition
    if args.train_dataset:
        config.skillsbench.train_dataset_for_overlap_check = args.train_dataset
    if args.injected_token_count is not None:
        config.skillsbench.declared_injected_token_count = args.injected_token_count
        config.skillsbench.injected_tokenizer = args.injected_tokenizer
    return config


def _protocol_runtime_metadata(
    config: EvalConfig,
    *,
    protocol: dict,
    condition: str,
    injected_token_count: int | None,
    injected_tokenizer: str,
) -> dict:
    model = config.agent.model
    settings = model.model_settings
    condition_contract = protocol["condition_configs"][condition]
    return {
        "experiment_protocol_sha256": protocol["protocol_sha256"],
        "evaluation_config_sha256": protocol["evaluation"]["resolved_config_sha256"],
        "task_order_sha256": protocol["evaluation"]["task_order_sha256"],
        "model_config_sha256": config_sha256(model),
        "agent_config_sha256": condition_contract["agent_config_sha256"],
        "prompt_sha256": condition_contract["prompt_sha256"],
        "requested_model": model.model_provider.model,
        "temperature": float(settings.temperature) if settings.temperature is not None else 0.0,
        "expected_trials_per_task": config.pass_k,
        "concurrency": config.concurrency,
        "judge_concurrency": config.judge_concurrency,
        "evaluation_dataset": config.data.dataset,
        "task_split_name": protocol["training"].get("split_name"),
        "train_dataset_for_overlap_check": protocol["training"]["dataset"],
        "experience_condition": condition,
        "injected_token_count": injected_token_count,
        "injected_tokenizer": injected_tokenizer,
    }


def validate_experiment_protocol_before_runner(
    args: argparse.Namespace,
    *,
    base_config: EvalConfig,
    config: EvalConfig,
) -> dict | None:
    """Fail before BaseBenchmark/model construction if a frozen protocol changed."""

    if not args.experiment_protocol:
        return None
    protocol = load_experiment_protocol(args.experiment_protocol, require_ready=True)
    evaluation = protocol["evaluation"]
    if evaluation.get("eval_config_name") != args.config_name:
        raise ValueError("Evaluation config name differs from signed experiment protocol")
    if evaluation.get("resolved_config_sha256") != config_sha256(base_config):
        raise ValueError("Resolved evaluation config differs from signed experiment protocol")
    if config.data.dataset != evaluation.get("dataset"):
        raise ValueError("Evaluation dataset differs from signed experiment protocol")
    condition = args.experience_condition
    if condition not in protocol.get("condition_configs", {}):
        raise ValueError("A signed experiment protocol requires a declared three-group condition")
    condition_contract = protocol["condition_configs"][condition]
    expected_agent_hash = condition_contract.get("agent_config_sha256")
    if not expected_agent_hash or config_sha256(config.agent) != expected_agent_hash:
        raise ValueError("Resolved agent config differs from the signed condition config")
    if args.train_dataset != protocol["training"]["dataset"]:
        raise ValueError("--train_dataset must exactly match the signed experiment protocol")
    if args.injected_token_count != condition_contract.get("declared_injected_token_count"):
        raise ValueError("Injected token count differs from the signed condition config")
    if args.injected_tokenizer != condition_contract.get("injected_tokenizer"):
        raise ValueError("Injected tokenizer differs from the signed condition config")
    if condition == "no_experience" and args.injected_token_count != 0:
        raise ValueError("no_experience must declare zero injected experience tokens")
    if args.exp_id != condition_contract.get("expected_exp_id"):
        raise ValueError("Evaluation exp_id differs from the signed condition config")
    shared = protocol["shared_parameters"]
    runtime_shared = {
        "pass_k": config.pass_k,
        "concurrency": config.concurrency,
        "judge_concurrency": config.judge_concurrency,
        "model_config_sha256": config_sha256(config.agent.model),
    }
    for field, actual in runtime_shared.items():
        if shared.get(field) != actual:
            raise ValueError(f"Runtime {field} differs from the signed shared parameters")

    training = protocol["training"]
    validation_mode = training.get("validation_mode")
    if validation_mode == "strict_practice_manifest":
        evidence = validate_practice_dataset_manifest(
            practice_dataset=training.get("dataset"),
            manifest_path=training.get("manifest_path"),
            split_name=training.get("split_name"),
            expected_record_count=training.get("record_count"),
            evaluation_dataset=config.data.dataset,
            db_url=config.db_url,
        )
        if evidence.get("practice_snapshot_sha256") != training.get("snapshot_sha256"):
            raise ValueError("Practice snapshot differs from signed experiment protocol")
        if evidence.get("evaluation_snapshot_sha256") != evaluation.get("snapshot_sha256"):
            raise ValueError("Evaluation exclusion snapshot differs from signed experiment protocol")
    elif validation_mode == "skillsbench_split_manifest":
        evidence = assert_datasets_disjoint(
            training["dataset"],
            config.data.dataset,
            db_url=config.db_url,
            split_manifest_path=training["manifest_path"],
            split_name=training["split_name"],
        )
        if evidence["train_task_ids_sha256"] != training["task_ids_set_sha256"]:
            raise ValueError("SkillsBench training inventory differs from signed protocol")
    else:
        raise ValueError(f"Unsupported experiment protocol validation_mode: {validation_mode!r}")

    validate_evaluation_inventory(evaluation, db_url=config.db_url)
    config.data.task_order = list(evaluation["task_order"])
    config.data.task_order_sha256 = evaluation["task_order_sha256"]
    config.data.protocol_metadata = _protocol_runtime_metadata(
        config,
        protocol=protocol,
        condition=condition,
        injected_token_count=args.injected_token_count,
        injected_tokenizer=args.injected_tokenizer,
    )
    # Recovery is allowed only for rows already stamped by this exact signed
    # condition. This prevents an old exp_id from silently reusing a different
    # model, prompt, dataset, or task order.
    SQLModelUtils.configure(config.db_url, initialize_schema=False)
    with SQLModelUtils.create_session() as session:
        existing = session.exec(
            select(EvaluationSample).where(EvaluationSample.exp_id == config.exp_id)
        ).all()
        allowed_stages = {"init", "rollout", "judged", "infra_error"}
        allowed_task_ids = set(evaluation["task_order"])
        task_contracts = {
            task["namespaced_task_id"]: task for task in evaluation["tasks"]
        }
        seen_trials: set[tuple[str, int]] = set()
        for row in existing:
            meta = row.meta
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    meta = {}
            if not isinstance(meta, dict):
                meta = {}
            expected_existing = config.data.protocol_metadata
            for field, expected_value in expected_existing.items():
                if meta.get(field) != expected_value:
                    raise ValueError(
                        f"Existing exp_id rows do not match signed protocol field {field}"
                    )
            if row.dataset != config.data.dataset:
                raise ValueError("Existing exp_id row belongs to a different evaluation dataset")
            if row.stage not in allowed_stages:
                raise ValueError(f"Existing exp_id row has unsupported recovery stage {row.stage!r}")
            raw_task_id = meta.get("task_id")
            if raw_task_id is None:
                raw_task_id = row.dataset_index
            namespaced_task_id = f"{row.dataset}:{raw_task_id}"
            if namespaced_task_id not in allowed_task_ids:
                raise ValueError("Existing exp_id row contains a task outside signed task_order")
            expected_question_hash = task_contracts[namespaced_task_id]["question_sha256"]
            actual_question_hash = hashlib.sha256((row.raw_question or "").encode("utf-8")).hexdigest()
            if actual_question_hash != expected_question_hash:
                raise ValueError("Existing exp_id row question differs from signed task inventory")
            trial_index = meta.get("trial_index")
            if (
                isinstance(trial_index, bool)
                or not isinstance(trial_index, int)
                or not 0 <= trial_index < config.pass_k
            ):
                raise ValueError("Existing exp_id row has an invalid trial_index")
            key = (namespaced_task_id, trial_index)
            if key in seen_trials:
                raise ValueError("Existing exp_id rows contain a duplicate task/trial pair")
            seen_trials.add(key)
    print(
        "Experiment protocol assertion passed: "
        + json.dumps(redact_sensitive_data({"condition": condition, "evidence": evidence}))
    )
    return protocol


async def main():
    parser = argparse.ArgumentParser()
    # config
    parser.add_argument("--config_name", type=str, default="ww", help="Configuration name for evaluation.")
    parser.add_argument("--exp_id", type=str, default=None, help="Experiment ID.")
    parser.add_argument("--agent_model", type=str, default=None, help="Agent model.")
    parser.add_argument("--agent_config", type=str, default=None, help="Agent config under configs/agents/.")
    parser.add_argument("--dataset", type=str, default=None, help="Dataset.")
    parser.add_argument("--pass_k", type=int, default=None, help="Rollout trials per dataset sample.")
    parser.add_argument("--concurrency", type=int, default=None, help="Test concurrency.")
    parser.add_argument("--judge_concurrency", type=int, default=None, help="Judge concurrency.")
    parser.add_argument(
        "--korgym_timeout_per_game",
        type=float,
        default=None,
        help="Wall-clock timeout in seconds for one KORGym game.",
    )
    parser.add_argument(
        "--allow_legacy_cache_reuse",
        action="store_true",
        help=(
            "Explicitly allow resuming pre-fingerprint evaluation rows. "
            "Prefer a new exp_id for reproducible experiments."
        ),
    )
    parser.add_argument(
        "--train_dataset",
        type=str,
        default=None,
        help="Dataset that produced learned experiences; required for sequential/clustered SkillsBench evaluation.",
    )
    parser.add_argument(
        "--experience_condition",
        choices=["no_experience", "sequential", "clustered", "task_local_skills"],
        default=None,
        help="Declared SkillsBench treatment; learned treatments require a disjoint train dataset.",
    )
    parser.add_argument("--injected_token_count", type=int, default=None)
    parser.add_argument("--injected_tokenizer", default="cl100k_base")
    parser.add_argument(
        "--experiment_protocol",
        default=None,
        help=(
            "Signed three-condition protocol; validates train/eval snapshots "
            "and task order before runner construction."
        ),
    )

    # eval steps
    parser.add_argument(
        "--step",
        type=str,
        default="all",
        choices=["all", "rollout", "judge", "retry-infra"],
        help="Evaluation step to run.",
    )
    args = parser.parse_args()

    base_config = ConfigLoader.load_eval_config(args.config_name)
    config = get_eval_config(args, base_config.model_copy(deep=True))
    validate_experiment_protocol_before_runner(args, base_config=base_config, config=config)

    runner = BaseBenchmark(config)
    if args.step == "all":
        # BaseBenchmark.main owns its cleanup in a finally block.
        await runner.main()
        return

    try:
        match args.step:
            case "rollout":
                runner.preprocess()
                await runner.rollout()
            case "judge":
                # Set stage=None to rejudge; rollout/judged are incremental.
                await runner.judge(stage="rollout")
                await runner.stat()
            case "retry-infra":
                await runner.retry_infra()
                await runner.judge(stage="rollout")
                await runner.stat()
            case _:
                raise ValueError(f"Unsupported stage: {args.step}")
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
