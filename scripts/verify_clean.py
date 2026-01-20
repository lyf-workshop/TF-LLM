#!/usr/bin/env python3
"""
验证并强制清理 Word Puzzle 评估缓存
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.utils import SQLModelUtils, get_logger
from utu.db import EvaluationSample
from sqlmodel import select, delete, func

logger = get_logger(__name__)

def verify_and_clean():
    exp_ids = ["word_puzzle_baseline_eval", "word_puzzle_practice_eval"]
    
    print("\n" + "=" * 80)
    print("验证并清理 Word Puzzle 评估缓存")
    print("=" * 80)
    
    with SQLModelUtils.create_session() as session:
        # 第1步：查找记录
        print(f"\n[1] 查找评估记录...")
        for exp_id in exp_ids:
            count = session.exec(
                select(func.count()).select_from(EvaluationSample).where(
                    EvaluationSample.exp_id == exp_id
                )
            ).one()
            print(f"  {exp_id}: {count} 条记录")
        
        # 第2步：查看一些样本详情
        print(f"\n[2] 查看样本详情（前2条）...")
        samples = session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id.in_(exp_ids)
            ).limit(2)
        ).all()
        
        for i, sample in enumerate(samples, 1):
            print(f"\n  样本 {i}:")
            print(f"    exp_id: {sample.exp_id}")
            print(f"    dataset: {sample.dataset}")
            print(f"    dataset_index: {sample.dataset_index}")
            print(f"    correct: {sample.correct}")
            print(f"    reward: {sample.reward}")
            print(f"    stage: {sample.stage}")
            if sample.meta:
                print(f"    meta keys: {list(sample.meta.keys())}")
        
        # 第3步：询问是否删除
        total_count = session.exec(
            select(func.count()).select_from(EvaluationSample).where(
                EvaluationSample.exp_id.in_(exp_ids)
            )
        ).one()
        
        if total_count == 0:
            print(f"\n✓ 数据已清空，无需删除")
            return
        
        print(f"\n[3] 是否删除这 {total_count} 条记录？")
        response = input("    输入 'yes' 确认删除: ")
        
        if response.lower() != 'yes':
            print("取消删除")
            return
        
        # 第4步：删除
        result = session.exec(
            delete(EvaluationSample).where(
                EvaluationSample.exp_id.in_(exp_ids)
            )
        )
        session.commit()
        
        print(f"\n✓ 已删除 {result.rowcount} 条记录")
        
        # 第5步：验证删除
        remaining = session.exec(
            select(func.count()).select_from(EvaluationSample).where(
                EvaluationSample.exp_id.in_(exp_ids)
            )
        ).one()
        
        if remaining == 0:
            print("✓ 验证成功：数据已完全清空")
        else:
            print(f"⚠️ 警告：仍有 {remaining} 条记录")
    
    print("\n" + "=" * 80)
    print("现在可以重新运行评估了！")
    print("  uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    verify_and_clean()

















