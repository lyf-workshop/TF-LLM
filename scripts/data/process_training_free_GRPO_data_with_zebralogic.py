"""
修改版数据加载脚本，包含 ZebraLogic 支持

这是 process_training_free_GRPO_data.py 的修改版本，添加了 ZebraLogic 数据集支持。

用法:
    # 加载所有数据集（包括 ZebraLogic）
    python scripts/data/process_training_free_GRPO_data_with_zebralogic.py
    
    # 只加载 ZebraLogic
    python scripts/data/process_training_free_GRPO_data_with_zebralogic.py --datasets ZebraLogic
"""

import argparse
import json
import os
import random
from typing import Any, Literal

from datasets import load_dataset
from huggingface_hub import snapshot_download
from sqlmodel import select

from utu.db.eval_datapoint import DatasetSample
from utu.utils import DIR_ROOT
from utu.utils.sqlmodel_utils import SQLModelUtils

rng = random.Random(42)
feat_path = "utu/train/dataset"


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
        transformed = {}
        for record in dataset.to_list():
            prompt = (
                record["prompt"][0]["content"]
                .replace(
                    "Solve the following math problem step by step. The last line of your response should be of the "
                    "form Answer: $Answer (without quotes) where $Answer is the answer to the problem.\n\n",
                    "",
                )
                .replace('\n\nRemember to put your answer on its own line after "Answer:".', "")
            )
            transformed[prompt] = record["reward_model"]["ground_truth"]
        dataset = [{"problem": problem, "groundtruth": answer} for problem, answer in transformed.items()]
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

    elif name == "ZebraLogic":
        # ⭐ 新增 ZebraLogic 数据集支持
        print(f"Loading ZebraLogic dataset from HuggingFace...")
        
        try:
            # 从 HuggingFace 加载
            hf_dataset = load_dataset("WildEval/ZebraLogic", split="train")
            print(f"Loaded {len(hf_dataset)} samples from ZebraLogic")
            
            # 显示第一个样本的结构（用于调试）
            if len(hf_dataset) > 0:
                print(f"Sample fields: {hf_dataset.column_names}")
            
            # 转换为标准格式
            dataset = []
            for idx, row in enumerate(hf_dataset):
                # 尝试多个可能的字段名
                problem = (
                    row.get("question") or 
                    row.get("problem") or 
                    row.get("puzzle") or 
                    row.get("input") or 
                    ""
                )
                
                groundtruth = (
                    row.get("answer") or 
                    row.get("solution") or 
                    row.get("output") or 
                    ""
                )
                
                # 确保非空
                if problem and groundtruth:
                    dataset.append({
                        "problem": str(problem),
                        "groundtruth": str(groundtruth)
                    })
                else:
                    print(f"Warning: Skipping sample {idx} - missing problem or answer")
            
            print(f"Processed {len(dataset)} valid samples")
            
            # 可选：打乱数据
            rng.shuffle(dataset)
            
        except Exception as e:
            print(f"Error loading ZebraLogic: {e}")
            print("Please check:")
            print("  1. Dataset exists at: https://huggingface.co/datasets/WildEval/ZebraLogic")
            print("  2. You have internet connection")
            print("  3. Try running: python scripts/data/check_zebralogic_format.py first")
            raise

    else:
        raise ValueError(f"Unknown dataset name: {name}")

    # Save on disk or database
    _save_dataset(name, dataset, save_type)
    return dataset


def main():
    parser = argparse.ArgumentParser(description="Load datasets for Training-Free GRPO")
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=["AIME24", "AIME25", "DAPO-Math-17k", "AFM_web_RL", "WebWalkerQA", "ZebraLogic"],
        help="Datasets to load (default: all including ZebraLogic)"
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("Loading datasets for Training-Free GRPO")
    print("=" * 70)
    print(f"Datasets to load: {', '.join(args.datasets)}")
    print()
    
    for name in args.datasets:
        try:
            print(f"\nLoading {name}...")
            data = load_data(name)
            print(f"✓ Loaded {len(data)} records for dataset {name}")
        except Exception as e:
            print(f"✗ Failed to load {name}: {e}")
    
    print("\n" + "=" * 70)
    print("Dataset loading complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()


