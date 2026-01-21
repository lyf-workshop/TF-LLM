#!/usr/bin/env python3
"""
清理旧的KORGym数据集并重新创建（修复meta字段问题）

用法:
    uv run python scripts/clean_and_recreate_datasets.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlmodel import delete
from utu.db import DatasetSample
from utu.utils import get_logger, SQLModelUtils

logger = get_logger(__name__)


def clean_korgym_datasets():
    """清理所有KORGym相关的数据集"""
    
    datasets_to_clean = [
        "KORGym-WordPuzzle-Eval-50",
        "KORGym-WordPuzzle-Train-100",
        "KORGym-AlphabeticalSorting-Eval-50",
        "KORGym-AlphabeticalSorting-Train-100",
        "KORGym-Wordle-Eval-50",
        "KORGym-Wordle-Train-100",
        # 旧的通用名称（如果存在）
        "KORGym-Eval-50",
        "KORGym-Train-100",
    ]
    
    print("\n" + "=" * 80)
    print("🧹 清理 KORGym 数据集")
    print("=" * 80)
    print("\n将删除以下数据集:")
    for ds in datasets_to_clean:
        print(f"  ❌ {ds}")
    print()
    
    response = input("确认删除？输入 'yes' 继续: ")
    if response.lower() != 'yes':
        print("❌ 取消操作")
        return False
    
    total_deleted = 0
    
    with SQLModelUtils.create_session() as session:
        for dataset_name in datasets_to_clean:
            samples = list(session.exec(
                delete(DatasetSample).where(
                    DatasetSample.dataset == dataset_name
                ).returning(DatasetSample)
            ))
            
            if samples:
                session.commit()
                print(f"  ✓ 删除 {len(samples)} 条记录: {dataset_name}")
                total_deleted += len(samples)
            else:
                print(f"  ℹ️  未找到数据集: {dataset_name}")
    
    print("\n" + "=" * 80)
    print(f"✅ 清理完成！共删除 {total_deleted} 条记录")
    print("=" * 80)
    print()
    
    return True


def recreate_datasets():
    """重新创建三个游戏的数据集"""
    from scripts.data.prepare_korgym_data import create_korgym_datasets
    
    games = [
        ("8-word_puzzle", "Word Puzzle"),
        ("22-alphabetical_sorting", "Alphabetical Sorting"),
        ("33-wordle", "Wordle"),
    ]
    
    print("🎮 重新创建数据集...")
    print()
    
    for game_id, game_name in games:
        print(f"\n{'='*80}")
        print(f"创建 {game_name} 数据集...")
        print(f"{'='*80}\n")
        
        create_korgym_datasets(
            game_name=game_id,
            eval_seeds_start=1,
            eval_seeds_end=50,
            train_seeds_start=51,
            train_seeds_end=150,
        )
    
    print("\n" + "=" * 80)
    print("🎉 所有数据集创建完成！")
    print("=" * 80)
    print()
    print("现在可以运行评估和训练了:")
    print("  - uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval")
    print("  - uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_eval")
    print("  - uv run python scripts/run_eval.py --config_name korgym/wordle_eval")
    print()


if __name__ == "__main__":
    # 1. 清理旧数据集
    if clean_korgym_datasets():
        # 2. 重新创建数据集
        recreate_datasets()





















