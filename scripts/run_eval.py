import argparse
import asyncio

from utu.config import ConfigLoader, EvalConfig
from utu.eval import BaseBenchmark
from utu.skillsbench_data import assert_datasets_disjoint


def get_eval_config(args: argparse.Namespace) -> EvalConfig:
    config = ConfigLoader.load_eval_config(args.config_name)
    if args.agent_config:
        config.agent = ConfigLoader.load_agent_config(args.agent_config)
    if args.exp_id:
        config.exp_id = args.exp_id
    if args.agent_model:
        config.agent.model.model_provider.model = args.agent_model
    if args.dataset:
        config.data.dataset = args.dataset
    if args.dataset_type:
        config.data.type = args.dataset_type
    if args.concurrency:
        config.concurrency = args.concurrency
    if args.judge_concurrency:
        config.judge_concurrency = args.judge_concurrency
    if args.experience_condition:
        config.skillsbench.experience_condition = args.experience_condition
    if args.injected_token_count is not None:
        config.skillsbench.declared_injected_token_count = args.injected_token_count
        config.skillsbench.injected_tokenizer = args.injected_tokenizer
    return config


async def main():
    parser = argparse.ArgumentParser()
    # config
    parser.add_argument("--config_name", type=str, default="ww", help="Configuration name for evaluation.")
    parser.add_argument("--exp_id", type=str, default=None, help="Experiment ID.")
    parser.add_argument("--agent_model", type=str, default=None, help="Agent model.")
    parser.add_argument("--agent_config", type=str, default=None, help="Agent config under configs/agents/.")
    parser.add_argument("--dataset", type=str, default=None, help="Dataset.")
    parser.add_argument("--dataset_type", type=str, default=None, help="Dataset type.")
    parser.add_argument("--concurrency", type=int, default=None, help="Test concurrency.")
    parser.add_argument("--judge_concurrency", type=int, default=None, help="Judge concurrency.")
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

    # eval steps
    parser.add_argument(
        "--step",
        type=str,
        default="all",
        choices=["all", "rollout", "judge", "retry-infra"],
        help="Evaluation step to run.",
    )
    args = parser.parse_args()

    config = get_eval_config(args)

    skillsbench = getattr(config, "skillsbench", None)
    if skillsbench and skillsbench.enabled and skillsbench.require_disjoint_train_eval:
        train_dataset = args.train_dataset or skillsbench.train_dataset_for_overlap_check
        learned_condition = skillsbench.experience_condition in {"sequential", "clustered"}
        if learned_condition and not train_dataset:
            raise ValueError(
                "SkillsBench learned-experience evaluation requires --train_dataset "
                "or skillsbench.train_dataset_for_overlap_check"
            )
        if train_dataset:
            evidence = assert_datasets_disjoint(
                train_dataset,
                config.data.dataset,
                db_url=config.db_url,
                split_manifest_path=skillsbench.task_split_manifest_path,
                split_name=skillsbench.task_split_name,
            )
            print(f"SkillsBench overlap assertion passed: {evidence}")

    runner = BaseBenchmark(config)
    match args.step:
        case "all":
            await runner.main()
        case "rollout":
            runner.preprocess()
            await runner.rollout()
        case "judge":
            await runner.judge(stage="rollout")  # set stage=None to rejudge; rollout or judged incrementally
            await runner.stat()
        case "retry-infra":
            await runner.retry_infra()
            await runner.judge(stage="rollout")
            await runner.stat()
        case _:
            raise ValueError(f"Unsupported stage: {args.step}")


if __name__ == "__main__":
    asyncio.run(main())
