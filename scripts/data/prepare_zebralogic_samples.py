#!/usr/bin/env python3
"""
准备 ZebraLogic 数据集样本
- 训练集：100道题（难度稍高）
- 测试集：30道题（难度中等）
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List

from datasets import load_dataset

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlmodel import select

from utu.db.eval_datapoint import DatasetSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def load_zebralogic_dataset():
    """加载 ZebraLogic 数据集"""
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
        print(f"📂 Loading from local file: {local_file_found}")
        dataset = load_dataset("parquet", data_files=local_file_found, split="train")
    else:
        print("📥 Loading from HuggingFace...")
        dataset = load_dataset("WildEval/ZebraLogic", split="test")
    
    return dataset


def analyze_difficulty(dataset):
    """分析数据集难度分布"""
    print("\n" + "="*60)
    print("📊 Dataset Structure Analysis")
    print("="*60)
    
    print(f"\nTotal samples: {len(dataset)}")
    print(f"\nAvailable fields: {list(dataset.features.keys())}")
    
    # 显示第一个样本
    print("\n" + "-"*60)
    print("Sample data (first entry):")
    print("-"*60)
    sample = dataset[0]
    for key, value in sample.items():
        if isinstance(value, str) and len(value) > 200:
            print(f"{key}: {value[:200]}...")
        else:
            print(f"{key}: {value}")
    
    # 检查是否有难度字段
    difficulty_fields = ['difficulty', 'level', 'complexity', 'stars', 'size']
    found_difficulty_field = None
    
    for field in difficulty_fields:
        if field in dataset.features:
            found_difficulty_field = field
            break
    
    if found_difficulty_field:
        print(f"\n✓ Found difficulty field: '{found_difficulty_field}'")
        # 统计难度分布
        difficulties = [item[found_difficulty_field] for item in dataset]
        from collections import Counter
        difficulty_counts = Counter(difficulties)
        print(f"\nDifficulty distribution:")
        for diff, count in sorted(difficulty_counts.items()):
            print(f"  {diff}: {count} samples")
        return found_difficulty_field
    else:
        print(f"\n⚠ No explicit difficulty field found")
        print(f"Available fields for difficulty estimation: {list(dataset.features.keys())}")
        return None


def select_samples_by_difficulty(
    dataset,
    difficulty_field: str = None,
    train_size: int = 100,
    test_size: int = 30,
):
    """
    根据难度选择样本
    - 训练集：高难度
    - 测试集：中等难度
    """
    import random
    
    if difficulty_field and difficulty_field in dataset.features:
        # 按难度筛选
        print(f"\n📌 Selecting samples based on '{difficulty_field}' field...")
        
        # 获取所有难度值
        difficulties = list(set([item[difficulty_field] for item in dataset]))
        difficulties_sorted = sorted(difficulties)
        
        print(f"Available difficulty levels: {difficulties_sorted}")
        
        # 分配难度级别
        if len(difficulties_sorted) >= 3:
            # 高难度：最高的几个级别
            high_diff = difficulties_sorted[-2:]
            # 中等难度：中间级别
            mid_diff = difficulties_sorted[len(difficulties_sorted)//2 : len(difficulties_sorted)//2 + 2]
        else:
            # 难度级别不够，使用简单策略
            high_diff = [difficulties_sorted[-1]] if difficulties_sorted else difficulties_sorted
            mid_diff = [difficulties_sorted[0]] if len(difficulties_sorted) > 1 else difficulties_sorted
        
        print(f"\n🔥 High difficulty levels for training: {high_diff}")
        print(f"⚖️  Medium difficulty levels for testing: {mid_diff}")
        
        # 筛选样本
        high_samples = [item for item in dataset if item[difficulty_field] in high_diff]
        mid_samples = [item for item in dataset if item[difficulty_field] in mid_diff]
        
        print(f"\nAvailable samples:")
        print(f"  High difficulty: {len(high_samples)}")
        print(f"  Medium difficulty: {len(mid_samples)}")
        
        # 采样
        if len(high_samples) < train_size:
            print(f"\n⚠ Warning: Not enough high difficulty samples ({len(high_samples)} < {train_size})")
            print(f"   Will use all available high difficulty samples")
            train_samples = high_samples
        else:
            train_samples = random.sample(high_samples, train_size)
        
        if len(mid_samples) < test_size:
            print(f"\n⚠ Warning: Not enough medium difficulty samples ({len(mid_samples)} < {test_size})")
            print(f"   Will use all available medium difficulty samples")
            test_samples = mid_samples
        else:
            test_samples = random.sample(mid_samples, test_size)
    
    else:
        # 没有难度字段，随机采样
        print(f"\n⚠ No difficulty field available, using random sampling...")
        all_indices = list(range(len(dataset)))
        random.shuffle(all_indices)
        
        train_indices = all_indices[:train_size]
        test_indices = all_indices[train_size:train_size + test_size]
        
        train_samples = [dataset[i] for i in train_indices]
        test_samples = [dataset[i] for i in test_indices]
    
    return train_samples, test_samples


def save_to_database(samples: List[dict], dataset_name: str, source: str = "training_free_grpo"):
    """保存样本到数据库"""
    with SQLModelUtils.create_session() as session:
        try:
            # 检查数据集是否已存在
            existing = session.exec(
                select(DatasetSample).where(DatasetSample.dataset == dataset_name)
            ).first()
            
            if existing:
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
                
                # 确保 question 和 answer 是字符串类型
                # 如果 answer 是字典（如 ZebraLogic 的 solution），转换为 JSON 字符串
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
                    source=source,
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
    parser = argparse.ArgumentParser(description="Prepare ZebraLogic samples for Training-Free GRPO")
    parser.add_argument("--train_size", type=int, default=100, help="Number of training samples")
    parser.add_argument("--test_size", type=int, default=30, help="Number of test samples")
    parser.add_argument("--train_name", type=str, default="ZebraLogic-Train-100", help="Training dataset name")
    parser.add_argument("--test_name", type=str, default="ZebraLogic-Test-30", help="Test dataset name")
    parser.add_argument("--analyze_only", action="store_true", help="Only analyze dataset, don't save")
    
    args = parser.parse_args()
    
    print("🚀 ZebraLogic Dataset Preparation")
    print("="*60)
    
    # 1. 加载数据集
    dataset = load_zebralogic_dataset()
    
    # 2. 分析难度分布
    difficulty_field = analyze_difficulty(dataset)
    
    if args.analyze_only:
        print("\n✓ Analysis complete (analyze_only mode)")
        return
    
    # 3. 选择样本
    print("\n" + "="*60)
    print("📝 Selecting Samples")
    print("="*60)
    
    train_samples, test_samples = select_samples_by_difficulty(
        dataset,
        difficulty_field=difficulty_field,
        train_size=args.train_size,
        test_size=args.test_size,
    )
    
    print(f"\n✓ Selected:")
    print(f"  Training: {len(train_samples)} samples")
    print(f"  Testing: {len(test_samples)} samples")
    
    # 4. 保存到数据库
    print("\n" + "="*60)
    print("💾 Saving to Database")
    print("="*60)
    
    success = True
    if train_samples:
        success &= save_to_database(train_samples, args.train_name)
    
    if test_samples:
        success &= save_to_database(test_samples, args.test_name)
    
    if success:
        print("\n" + "="*60)
        print("✅ All Done!")
        print("="*60)
        print(f"\nDatasets created:")
        print(f"  1. {args.train_name}: {len(train_samples)} samples (for training)")
        print(f"  2. {args.test_name}: {len(test_samples)} samples (for evaluation)")
        print(f"\nNext steps:")
        print(f"  1. Update practice config to use '{args.train_name}'")
        print(f"  2. Update eval config to use '{args.test_name}'")
        print(f"  3. Run: uv run python scripts/run_practice.py --config practice/logic_reasoning_zebralogic.yaml")


if __name__ == "__main__":
    main()

