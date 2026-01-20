#!/usr/bin/env python3
"""
准备 ZebraLogic 中下等难度100题数据集
从原始1000道题目中选择中下等难度的100道题目用于训练/评估
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import List, Optional

from datasets import load_dataset

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlmodel import select

from utu.db.eval_datapoint import DatasetSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def load_zebralogic_dataset():
    """加载 ZebraLogic 数据集（原始1000题）"""
    print("📂 Loading ZebraLogic dataset...")
    
    # 支持多种路径格式（Windows 和 WSL）
    local_paths = [
        "ZebraLogic/grid_mode/test-00000-of-00001.parquet",  # 相对路径
        "F:\\youtu-agent\\ZebraLogic\\grid_mode\\test-00000-of-00001.parquet",  # Windows
        "/mnt/f/youtu-agent/ZebraLogic/grid_mode/test-00000-of-00001.parquet",  # WSL
    ]
    
    local_file_found = None
    for path in local_paths:
        if os.path.exists(path):
            local_file_found = path
            break
    
    if local_file_found:
        print(f"✓ Loading from local file: {local_file_found}")
        dataset = load_dataset("parquet", data_files=local_file_found, split="train")
    else:
        print("📥 Loading from HuggingFace (this may take a while)...")
        dataset = load_dataset("WildEval/ZebraLogic", split="test")
    
    print(f"✓ Loaded {len(dataset)} samples")
    return dataset


def analyze_difficulty(dataset):
    """
    分析数据集难度分布
    
    Returns:
        difficulty_field: 难度字段名称，如果找到的话
        difficulty_stats: 难度分布统计
    """
    print("\n" + "="*70)
    print("📊 Dataset Difficulty Analysis")
    print("="*70)
    
    print(f"\nTotal samples: {len(dataset)}")
    print(f"Available fields: {list(dataset.features.keys())}")
    
    # 显示第一个样本（部分内容）
    if len(dataset) > 0:
        print("\n" + "-"*70)
        print("Sample data (first entry - truncated):")
        print("-"*70)
        sample = dataset[0]
        for key, value in sample.items():
            if isinstance(value, str) and len(value) > 100:
                print(f"  {key}: {value[:100]}...")
            elif isinstance(value, dict):
                print(f"  {key}: {str(value)[:100]}...")
            else:
                print(f"  {key}: {value}")
    
    # 检查可能的难度字段
    difficulty_fields = ['difficulty', 'level', 'complexity', 'stars', 'size', 'puzzle_size']
    found_difficulty_field = None
    
    for field in difficulty_fields:
        if field in dataset.features:
            found_difficulty_field = field
            break
    
    difficulty_stats = {}
    
    if found_difficulty_field:
        print(f"\n✓ Found difficulty field: '{found_difficulty_field}'")
        
        # 统计难度分布
        from collections import Counter
        difficulties = [item[found_difficulty_field] for item in dataset]
        difficulty_counts = Counter(difficulties)
        
        print(f"\nDifficulty distribution:")
        for diff in sorted(difficulty_counts.keys()):
            count = difficulty_counts[diff]
            percentage = (count / len(dataset)) * 100
            print(f"  {diff}: {count} samples ({percentage:.1f}%)")
        
        difficulty_stats = {
            'field': found_difficulty_field,
            'counts': difficulty_counts,
            'sorted_levels': sorted(difficulty_counts.keys())
        }
    else:
        print(f"\n⚠ No explicit difficulty field found")
        print(f"Will estimate difficulty based on available metrics...")
        
        # 尝试基于其他指标估算难度（如puzzle长度等）
        if 'puzzle' in dataset.features:
            print("\nEstimating difficulty based on puzzle length...")
            lengths = []
            for item in dataset:
                puzzle = item.get('puzzle', '')
                if isinstance(puzzle, str):
                    lengths.append(len(puzzle))
                elif isinstance(puzzle, dict):
                    lengths.append(len(str(puzzle)))
                else:
                    lengths.append(0)
            
            # 按长度分为3个难度级别
            sorted_lengths = sorted(lengths)
            low_threshold = sorted_lengths[len(sorted_lengths) // 3]
            high_threshold = sorted_lengths[2 * len(sorted_lengths) // 3]
            
            print(f"\nEstimated difficulty thresholds (by length):")
            print(f"  Low: < {low_threshold} chars")
            print(f"  Medium: {low_threshold} - {high_threshold} chars")
            print(f"  High: > {high_threshold} chars")
            
            difficulty_stats = {
                'field': 'estimated_difficulty',
                'method': 'puzzle_length',
                'low_threshold': low_threshold,
                'high_threshold': high_threshold
            }
    
    return found_difficulty_field, difficulty_stats


def select_medium_lower_samples(
    dataset,
    difficulty_field: Optional[str] = None,
    difficulty_stats: dict = None,
    num_samples: int = 100,
    seed: int = 42,
):
    """
    选择中下等难度的样本
    
    策略：
    - 如果有明确的难度字段：选择中等偏下的难度级别
    - 如果没有难度字段：基于puzzle长度等指标估算难度
    
    Args:
        dataset: 数据集
        difficulty_field: 难度字段名称
        difficulty_stats: 难度统计信息
        num_samples: 要选择的样本数量
        seed: 随机种子
    
    Returns:
        selected_samples: 选中的样本列表
    """
    random.seed(seed)
    
    print("\n" + "="*70)
    print("📝 Selecting Medium-Lower Difficulty Samples")
    print("="*70)
    
    if difficulty_field and difficulty_field in dataset.features:
        # 方法1: 基于明确的难度字段
        print(f"Selection strategy: Using '{difficulty_field}' field")
        
        sorted_levels = difficulty_stats['sorted_levels']
        total_levels = len(sorted_levels)
        
        print(f"\nAvailable difficulty levels: {sorted_levels}")
        
        # 选择中下等难度：根据难度级别数量决定
        if total_levels >= 5:
            # 5个或更多级别：选择第2、3个级别（跳过最简单的）
            target_levels = sorted_levels[1:3]
        elif total_levels >= 3:
            # 3-4个级别：选择第1、2个级别
            target_levels = sorted_levels[:2]
        else:
            # 2个或更少级别：选择较低的级别
            target_levels = [sorted_levels[0]]
        
        print(f"✓ Selected difficulty levels for sampling: {target_levels}")
        print(f"  (Medium-lower difficulty range)")
        
        # 筛选目标难度的样本
        target_samples = [
            item for item in dataset 
            if item[difficulty_field] in target_levels
        ]
        
        print(f"\n✓ Found {len(target_samples)} samples in target difficulty range")
        
        # 采样
        if len(target_samples) <= num_samples:
            print(f"  Using all {len(target_samples)} available samples")
            selected_samples = target_samples
        else:
            print(f"  Randomly sampling {num_samples} from {len(target_samples)} samples")
            selected_samples = random.sample(target_samples, num_samples)
    
    elif difficulty_stats and 'method' in difficulty_stats:
        # 方法2: 基于估算的难度
        print(f"Selection strategy: Using estimated difficulty ({difficulty_stats['method']})")
        
        low_threshold = difficulty_stats['low_threshold']
        high_threshold = difficulty_stats['high_threshold']
        
        # 选择中等难度（偏下）：略高于低阈值到中位数
        target_min = low_threshold
        target_max = (low_threshold + high_threshold) / 2
        
        print(f"\n✓ Target difficulty range: {target_min:.0f} - {target_max:.0f} chars")
        
        # 筛选样本
        target_samples = []
        for item in dataset:
            puzzle = item.get('puzzle', '')
            if isinstance(puzzle, str):
                length = len(puzzle)
            elif isinstance(puzzle, dict):
                length = len(str(puzzle))
            else:
                length = 0
            
            if target_min <= length <= target_max:
                target_samples.append(item)
        
        print(f"\n✓ Found {len(target_samples)} samples in target range")
        
        # 采样
        if len(target_samples) <= num_samples:
            print(f"  Using all {len(target_samples)} available samples")
            selected_samples = target_samples
        else:
            print(f"  Randomly sampling {num_samples} from {len(target_samples)} samples")
            selected_samples = random.sample(target_samples, num_samples)
    
    else:
        # 方法3: 随机采样（备用）
        print("⚠ No difficulty information available, using random sampling")
        all_samples = list(dataset)
        selected_samples = random.sample(all_samples, min(num_samples, len(all_samples)))
    
    return selected_samples


def save_to_database(samples: List[dict], dataset_name: str, overwrite: bool = False):
    """保存样本到数据库"""
    print("\n" + "="*70)
    print("💾 Saving to Database")
    print("="*70)
    
    with SQLModelUtils.create_session() as session:
        try:
            # 检查数据集是否已存在
            existing = session.exec(
                select(DatasetSample).where(DatasetSample.dataset == dataset_name)
            ).first()
            
            if existing:
                if not overwrite:
                    print(f"\n⚠ Dataset '{dataset_name}' already exists in database!")
                    response = input("Do you want to overwrite it? (yes/no): ")
                    if response.lower() != 'yes':
                        print("❌ Aborted")
                        return False
                
                # 删除现有数据
                existing_all = session.exec(
                    select(DatasetSample).where(DatasetSample.dataset == dataset_name)
                ).all()
                for item in existing_all:
                    session.delete(item)
                session.commit()
                print(f"✓ Deleted {len(existing_all)} existing samples")
            
            # 添加新样本
            new_samples = []
            for idx, sample in enumerate(samples):
                # 将 puzzle 作为 question，solution 作为 answer
                question = sample.get('puzzle', sample.get('question', ''))
                answer = sample.get('solution', sample.get('answer', ''))
                
                # 确保是字符串类型
                if isinstance(question, dict):
                    question = json.dumps(question, ensure_ascii=False)
                else:
                    question = str(question) if question else ""
                
                if isinstance(answer, dict):
                    answer = json.dumps(answer, ensure_ascii=False)
                else:
                    answer = str(answer) if answer else ""
                
                db_sample = DatasetSample(
                    dataset=dataset_name,
                    index=idx + 1,  # 索引从1开始
                    source="training_free_grpo",
                    question=question,
                    answer=answer,
                )
                new_samples.append(db_sample)
            
            session.add_all(new_samples)
            session.commit()
            print(f"✅ Successfully saved {len(new_samples)} samples to '{dataset_name}'")
            return True
        
        except Exception as e:
            session.rollback()
            print(f"❌ Error saving to database: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    parser = argparse.ArgumentParser(
        description="从ZebraLogic原始数据集（1000题）中选择中下等难度的100道题目"
    )
    parser.add_argument(
        "--num_samples",
        type=int,
        default=100,
        help="要选择的样本数量（默认：100）"
    )
    parser.add_argument(
        "--dataset_name",
        type=str,
        default="ZebraLogic-MediumLower-100",
        help="保存的数据集名称"
    )
    parser.add_argument(
        "--analyze_only",
        action="store_true",
        help="只分析数据集，不保存"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="随机种子（默认：42）"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="如果数据集已存在，自动覆盖（不询问）"
    )
    
    args = parser.parse_args()
    
    print("🚀 ZebraLogic Medium-Lower Difficulty Dataset Preparation")
    print("="*70)
    print(f"Target: {args.num_samples} samples of medium-lower difficulty")
    print("="*70)
    
    # 1. 加载原始数据集
    dataset = load_zebralogic_dataset()
    
    # 2. 分析难度分布
    difficulty_field, difficulty_stats = analyze_difficulty(dataset)
    
    if args.analyze_only:
        print("\n✓ Analysis complete (--analyze_only mode)")
        print("\nTo create the dataset, run:")
        print(f"  uv run python scripts/data/prepare_zebralogic_medium_lower_100.py --num_samples {args.num_samples}")
        return
    
    # 3. 选择中下等难度样本
    selected_samples = select_medium_lower_samples(
        dataset,
        difficulty_field=difficulty_field,
        difficulty_stats=difficulty_stats,
        num_samples=args.num_samples,
        seed=args.seed,
    )
    
    print(f"\n✓ Selected {len(selected_samples)} samples")
    
    # 4. 保存到数据库
    success = save_to_database(
        selected_samples,
        args.dataset_name,
        overwrite=args.overwrite
    )
    
    if success:
        print("\n" + "="*70)
        print("✅ All Done!")
        print("="*70)
        print(f"\n📊 Dataset created:")
        print(f"   Name: {args.dataset_name}")
        print(f"   Samples: {len(selected_samples)}")
        print(f"   Difficulty: Medium-Lower")
        print(f"\n📝 Next steps:")
        print(f"   1. Update your training config to use '{args.dataset_name}'")
        print(f"   2. Example:")
        print(f"      data:")
        print(f"        practice_dataset_name: \"{args.dataset_name}\"")
        print(f"        batch_size: {min(30, len(selected_samples))}")
        print(f"   3. Run training:")
        print(f"      uv run python scripts/run_training_free_GRPO.py --config_name your_config")


if __name__ == "__main__":
    main()

