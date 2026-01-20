#!/usr/bin/env python3
"""
简化版调试脚本 - 检查word_puzzle评估失败原因
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import select
from utu.db import EvaluationSample, DatasetSample
from utu.utils import SQLModelUtils

def check_issue():
    print("\n" + "=" * 80)
    print("检查 Word Puzzle 评估问题")
    print("=" * 80)
    
    with SQLModelUtils.create_session() as session:
        # 1. 检查数据集
        print("\n[1] 检查数据集...")
        dataset_samples = list(session.exec(
            select(DatasetSample).where(
                DatasetSample.dataset == "KORGym-WordPuzzle-Eval-50"
            ).limit(3)
        ))
        
        if not dataset_samples:
            print("❌ 数据集 'KORGym-WordPuzzle-Eval-50' 不存在！")
            print("   需要运行: uv run python scripts/data/prepare_korgym_data.py --game_name '8-word_puzzle'")
            return
        
        print(f"✓ 找到数据集，样本数: {len(dataset_samples)}")
        print(f"  第一个样本的meta: {dataset_samples[0].meta}")
        
        # 2. 检查评估样本
        print("\n[2] 检查评估样本...")
        eval_samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == "word_puzzle_baseline_eval"
            ).limit(2)
        ))
        
        if not eval_samples:
            print("❌ 未找到评估结果")
            return
        
        print(f"✓ 找到 {len(eval_samples)} 个评估样本")
        
        for i, sample in enumerate(eval_samples, 1):
            print(f"\n样本 {i}:")
            print(f"  问题: {sample.raw_question[:100]}...")
            print(f"  回答: {sample.response[:150] if sample.response else 'None'}...")
            print(f"  正确: {sample.correct}")
            print(f"  奖励: {sample.reward}")
            print(f"  meta中的seed: {sample.meta.get('seed') if sample.meta else 'None'}")
            print(f"  meta中的game_seed: {sample.meta.get('game_seed') if sample.meta else 'None'}")

if __name__ == "__main__":
    check_issue()

















