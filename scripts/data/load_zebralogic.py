"""
加载 ZebraLogic 数据集用于 Training-Free GRPO

用法:
    python scripts/data/load_zebralogic.py
    
或指定数据集分割:
    python scripts/data/load_zebralogic.py --split train
    python scripts/data/load_zebralogic.py --split test
"""

import argparse
import json
from typing import Any, Literal

from datasets import load_dataset
from sqlmodel import select

from utu.db.eval_datapoint import DatasetSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def _check_exists(name: str) -> list[DatasetSample]:
    """检查数据集是否已存在"""
    with SQLModelUtils.create_session() as session:
        samples = session.exec(select(DatasetSample).where(DatasetSample.dataset == name)).all()
    return samples


def load_zebralogic(dataset_name: str = "ZebraLogic", split: str = "train", max_samples: int | None = None):
    """
    加载 ZebraLogic 数据集
    
    Args:
        dataset_name: 保存到数据库的数据集名称
        split: 数据集分割 (train/test/validation)
        max_samples: 最大样本数（用于采样），None 表示加载全部
    """
    # 检查是否已存在
    existing = _check_exists(dataset_name)
    if existing:
        print(f"Dataset {dataset_name} already exists with {len(existing)} samples, skipping load.")
        return existing
    
    print(f"Loading ZebraLogic dataset from HuggingFace...")
    
    try:
        # 从本地 parquet 文件加载数据集（如果已下载）
        # 或从 HuggingFace 加载
        
        import os
        
        # 支持多种路径格式（Windows 和 WSL）
        local_paths = [
            "ZebraLogic/grid_mode/test-00000-of-00001.parquet",  # 相对路径
            "F:\\youtu-agent\\ZebraLogic\\grid_mode\\test-00000-of-00001.parquet",  # Windows 绝对路径
            "/mnt/f/youtu-agent/ZebraLogic/grid_mode/test-00000-of-00001.parquet",  # WSL 路径
        ]
        
        local_file_found = None
        for path in local_paths:
            if os.path.exists(path):
                local_file_found = path
                break
        
        if local_file_found:
            print(f"Loading from local file: {local_file_found}")
            dataset = load_dataset("parquet", data_files=local_file_found, split="train")
        else:
            # 从 HuggingFace 加载
            print(f"Local file not found (tried {len(local_paths)} paths). Loading from HuggingFace...")
            dataset = load_dataset("WildEval/ZebraLogic", split=split)
        print(f"Successfully loaded {len(dataset)} samples from split '{split}'")
        
        # 查看数据集结构（第一次运行时）
        print("\nDataset structure (first sample):")
        if len(dataset) > 0:
            first_sample = dataset[0]
            print(json.dumps(first_sample, indent=2, ensure_ascii=False)[:500] + "...")
            print(f"\nAvailable fields: {dataset.column_names}")
        
        # 转换数据格式
        processed_samples = []
        
        for idx, row in enumerate(dataset):
            # 尝试多个可能的字段名来获取问题和答案
            # 根据实际数据集结构调整这些字段名
            
            # 获取问题
            problem = (
                row.get("question") or 
                row.get("problem") or 
                row.get("puzzle") or 
                row.get("input") or 
                row.get("text") or
                ""
            )
            
            # 获取答案
            groundtruth = (
                row.get("answer") or 
                row.get("solution") or 
                row.get("output") or 
                row.get("label") or 
                row.get("target") or
                ""
            )
            
            # 确保是字符串类型
            problem = str(problem) if problem else ""
            groundtruth = str(groundtruth) if groundtruth else ""
            
            # 跳过空样本
            if not problem:
                print(f"Warning: Skipping sample {idx} - empty problem")
                continue
            
            # 创建数据样本
            sample = DatasetSample(
                dataset=dataset_name,
                index=idx,
                source="training_free_grpo",
                question=problem,
                answer=groundtruth,
                # 可选字段
                level=row.get("difficulty") or row.get("level", 0),
                topic=row.get("category") or row.get("topic", ""),
                meta=json.dumps({
                    k: v for k, v in row.items() 
                    if k not in ["question", "problem", "answer", "solution"]
                }, ensure_ascii=False) if row else None
            )
            
            processed_samples.append(sample)
            
            # 如果设置了最大样本数，达到后停止
            if max_samples and len(processed_samples) >= max_samples:
                print(f"Reached max_samples limit: {max_samples}")
                break
        
        print(f"\nProcessed {len(processed_samples)} samples")
        
        # 保存到数据库
        if processed_samples:
            print(f"Saving to database...")
            with SQLModelUtils.create_session() as session:
                session.add_all(processed_samples)
                session.commit()
            print(f"✓ Successfully saved {len(processed_samples)} samples to database")
        else:
            print("⚠ No samples to save")
        
        return processed_samples
        
    except Exception as e:
        print(f"Error loading ZebraLogic dataset: {e}")
        print("\nTroubleshooting:")
        print("1. Check if the dataset exists: https://huggingface.co/datasets/WildEval/ZebraLogic")
        print("2. Verify the split name (try 'train', 'test', or 'validation')")
        print("3. Check your internet connection")
        print("4. Try manual download: git clone https://huggingface.co/datasets/WildEval/ZebraLogic")
        raise


def create_zebralogic_sample(dataset_name: str = "ZebraLogic-100", source_name: str = "ZebraLogic", num_samples: int = 100, seed: int = 42):
    """
    从 ZebraLogic 数据集中采样创建子集
    
    Args:
        dataset_name: 新数据集名称
        source_name: 源数据集名称
        num_samples: 采样数量
        seed: 随机种子
    """
    import random
    
    # 检查源数据集是否存在
    with SQLModelUtils.create_session() as session:
        source_samples = session.exec(
            select(DatasetSample).where(DatasetSample.dataset == source_name)
        ).all()
        
        if not source_samples:
            print(f"Source dataset {source_name} not found. Please load it first.")
            return
        
        # 检查目标数据集是否已存在
        existing = session.exec(
            select(DatasetSample).where(DatasetSample.dataset == dataset_name)
        ).all()
        
        if existing:
            print(f"Dataset {dataset_name} already exists with {len(existing)} samples.")
            return
        
        print(f"Sampling {num_samples} from {len(source_samples)} samples...")
        
        # 随机采样
        rng = random.Random(seed)
        sampled = rng.sample(source_samples, min(num_samples, len(source_samples)))
        
        # 创建新样本
        new_samples = []
        for idx, sample in enumerate(sampled):
            new_sample = DatasetSample(
                dataset=dataset_name,
                index=idx,
                source="training_free_grpo",
                question=sample.question,
                answer=sample.answer,
                level=sample.level,
                topic=sample.topic,
                meta=sample.meta
            )
            new_samples.append(new_sample)
        
        # 保存
        session.add_all(new_samples)
        session.commit()
        
        print(f"✓ Successfully created {dataset_name} with {len(new_samples)} samples")


def main():
    parser = argparse.ArgumentParser(description="Load ZebraLogic dataset for Training-Free GRPO")
    parser.add_argument(
        "--dataset_name",
        type=str,
        default="ZebraLogic",
        help="Name to save the dataset as in the database"
    )
    parser.add_argument(
        "--split",
        type=str,
        default="train",
        help="Dataset split to load (train/test/validation)"
    )
    parser.add_argument(
        "--max_samples",
        type=int,
        default=None,
        help="Maximum number of samples to load (None for all)"
    )
    parser.add_argument(
        "--create_sample",
        action="store_true",
        help="Create a sampled subset after loading"
    )
    parser.add_argument(
        "--sample_size",
        type=int,
        default=100,
        help="Size of the sampled subset"
    )
    parser.add_argument(
        "--sample_name",
        type=str,
        default="ZebraLogic-100",
        help="Name for the sampled subset"
    )
    
    args = parser.parse_args()
    
    # 加载数据集
    samples = load_zebralogic(
        dataset_name=args.dataset_name,
        split=args.split,
        max_samples=args.max_samples
    )
    
    # 如果需要，创建采样子集
    if args.create_sample and samples:
        create_zebralogic_sample(
            dataset_name=args.sample_name,
            source_name=args.dataset_name,
            num_samples=args.sample_size
        )


if __name__ == "__main__":
    main()

