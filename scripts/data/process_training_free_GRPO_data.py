import argparse
import json
import os
import random
from typing import Any, Literal

from datasets import load_dataset
from huggingface_hub import snapshot_download
from sqlmodel import select

from utu import utils as utu_utils
from utu.db.eval_datapoint import DatasetSample

DIR_ROOT = utu_utils.DIR_ROOT
SQLModelUtils = utu_utils.SQLModelUtils

rng = random.Random(42)
feat_path = "utu/train/dataset"
DATASET_NAMES = ("AIME24", "AIME25", "DAPO-Math-17k", "AFM_web_RL", "WebWalkerQA")
UPSTREAM_METADATA_KEY = "_tf_llm_upstream"


def _transform_dapo_record(record: dict[str, Any]) -> dict[str, Any]:
    """Keep the native DAPO provenance that the historical importer dropped.

    ``ability`` is the only upstream field that can justify a broad domain
    label.  It is deliberately stored as evidence rather than converted to a
    fine-grained ``task_family``: DAPO does not provide such a label.
    """

    data_source = record.get("data_source")
    ability = record.get("ability")
    extra_info = record.get("extra_info")
    if not isinstance(data_source, str) or not data_source.strip():
        raise ValueError("DAPO record is missing non-empty upstream data_source")
    if not isinstance(ability, str) or not ability.strip():
        raise ValueError("DAPO record is missing non-empty upstream ability")
    if not isinstance(extra_info, dict):
        raise ValueError("DAPO record is missing upstream extra_info mapping")

    prompt = record.get("prompt")
    if not isinstance(prompt, list) or not prompt or not isinstance(prompt[0], dict):
        raise ValueError("DAPO record has invalid prompt structure")
    prompt_content = prompt[0].get("content")
    reward_model = record.get("reward_model")
    if not isinstance(prompt_content, str) or not isinstance(reward_model, dict):
        raise ValueError("DAPO record has invalid prompt or reward_model")
    if "ground_truth" not in reward_model:
        raise ValueError("DAPO record reward_model is missing ground_truth")

    problem = prompt_content.replace(
        "Solve the following math problem step by step. The last line of your response should be of the "
        "form Answer: $Answer (without quotes) where $Answer is the answer to the problem.\n\n",
        "",
    ).replace('\n\nRemember to put your answer on its own line after "Answer:".', "")
    return {
        "problem": problem,
        "groundtruth": reward_model["ground_truth"],
        "meta": {
            UPSTREAM_METADATA_KEY: {
                "data_source": data_source,
                "ability": ability,
                "extra_info": extra_info,
            }
        },
    }


def _check_exists(name: str, save_type: Literal["db", "file"]) -> list[DatasetSample] | list[dict[str, Any]]:
    if save_type == "db":
        with SQLModelUtils.create_session() as session:
            samples = session.exec(select(DatasetSample).where(DatasetSample.dataset == name)).all()
        return samples
    elif save_type == "file":
        cache_path = os.path.join(feat_path, f"{name}.jsonl")
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as handle:
                return [json.loads(line) for line in handle.readlines()]
        return []
    else:
        raise ValueError(f"Unknown type: {type}")


def _save_dataset(
    name: str, data: list[DatasetSample] | list[dict[str, Any]], save_type: Literal["db", "file"]
) -> None:
    if save_type == "db":
        with SQLModelUtils.create_session() as session:
            samples = []
            for idx, record in enumerate(data):
                sample = DatasetSample(
                    dataset=name,
                    index=idx,
                    source="training_free_grpo",
                    question=record["problem"],
                    answer=record["groundtruth"],
                    topic=record.get("topic", ""),
                    level=record.get("level", 0),
                    file_name=record.get("file_name", ""),
                    meta=record.get("meta"),
                )
                samples.append(sample)
            session.add_all(samples)
            session.commit()
    elif save_type == "file":
        cache_path = os.path.join(feat_path, f"{name}.jsonl")
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as handle:
            for record in data:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    else:
        raise ValueError(f"Unknown type: {save_type}")


def load_data(name: str, save_type: Literal["db", "file"] = "db") -> list[DatasetSample] | list[dict[str, Any]]:
    if samples := _check_exists(name, save_type):
        print(f"Dataset {name} already exists in {save_type}, skipping load.")
        return samples

    if name == "AIME24":
        dataset = load_dataset("HuggingFaceH4/aime_2024", split="train")
        dataset = [{"problem": row["problem"], "groundtruth": row["answer"]} for row in dataset.to_list()]

    elif name == "AIME25":
        dataset = load_dataset("yentinglin/aime_2025", split="train")
        dataset = [{"problem": row["problem"], "groundtruth": row["answer"]} for row in dataset.to_list()]

    elif name == "DAPO-Math-17k":
        local_dir = DIR_ROOT / "data" / "DAPO-Math-17k"
        snapshot_download(
            repo_id="BytedTsinghua-SIA/DAPO-Math-17k",
            repo_type="dataset",
            local_dir=str(local_dir),
            ignore_patterns=[".gitattributes", "README.md"],
        )
        dataset = load_dataset("parquet", data_files=str(local_dir / "data" / "dapo-math-17k.parquet"))["train"]
        transformed: dict[str, dict[str, Any]] = {}
        for record in dataset.to_list():
            transformed_record = _transform_dapo_record(record)
            # Preserve the historical last-write-wins de-duplication semantics
            # while retaining the winning row's complete upstream evidence.
            transformed[transformed_record["problem"]] = transformed_record
        dataset = list(transformed.values())
        rng.shuffle(dataset)

    elif name == "AFM_web_RL":
        dataset = load_dataset("PersonalAILab/AFM-WebAgent-RL-Dataset", split="train")
        records = []
        for idx, row in enumerate(dataset.to_list(), start=1):
            if len(row["extra_info"]["answer"]) != 1:
                continue
            records.append(
                {
                    "id": idx,
                    "problem": row["extra_info"]["question"],
                    "groundtruth": row["extra_info"]["answer"][0],
                }
            )
        rng.shuffle(records)
        for idx, record in enumerate(records, start=1):
            record["source_id"] = record["id"]
            record["id"] = idx
            record["index"] = idx
        dataset = records

    elif name == "WebWalkerQA":
        dataset = load_dataset("callanwu/WebWalkerQA", split="main")
        level_map = {"easy": 1, "medium": 2, "hard": 3}
        buckets = {1: [], 2: [], 3: []}
        for idx, row in enumerate(dataset.to_list(), start=1):
            buckets[level_map[row["info"]["difficulty_level"]]].append(
                {
                    "id": idx,
                    "problem": row["question"],
                    "groundtruth": row["answer"],
                    "level": level_map[row["info"]["difficulty_level"]],
                    "root_url": row["root_url"],
                    "info": json.dumps(row["info"], ensure_ascii=False),
                }
            )
        for bucket in buckets.values():
            rng.shuffle(bucket)
        ratio_pattern = [1] * 4 + [2] * 7 + [3] * 6
        ordered: list[dict[str, Any]] = []
        while any(buckets.values()):
            for level in ratio_pattern:
                if buckets[level]:
                    ordered.append(buckets[level].pop())
        for idx, record in enumerate(ordered, start=1):
            record["source_id"] = record["id"]
            record["id"] = idx
            record["index"] = idx
        dataset = ordered

    else:
        raise ValueError(f"Unknown dataset name: {name}")

    # Save on disk or database
    _save_dataset(name, dataset, save_type)
    return dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare TF-GRPO datasets")
    parser.add_argument(
        "--datasets",
        nargs="+",
        choices=DATASET_NAMES,
        default=list(DATASET_NAMES),
        help="Datasets to prepare; without this option all supported datasets are loaded.",
    )
    parser.add_argument("--save-type", choices=("db", "file"), default="db")
    args = parser.parse_args()

    for name in args.datasets:
        data = load_data(name, save_type=args.save_type)
        print(f"Loaded {len(data)} records for dataset {name}")


if __name__ == "__main__":
    main()
