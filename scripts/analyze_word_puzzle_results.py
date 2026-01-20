#!/usr/bin/env python3
"""
分析 Word Puzzle 评估结果
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.utils import SQLModelUtils, get_logger
from utu.db import EvaluationSample
from sqlmodel import select, func

logger = get_logger(__name__)

def analyze_results(exp_id: str = "word_puzzle_baseline_eval"):
    print("\n" + "=" * 80)
    print(f"分析评估结果: {exp_id}")
    print("=" * 80)
    
    with SQLModelUtils.create_session() as session:
        # 获取所有样本
        samples = session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == exp_id
            ).order_by(EvaluationSample.id)
        ).all()
        
        if not samples:
            print(f"❌ 未找到评估结果: {exp_id}")
            return
        
        print(f"\n总样本数: {len(samples)}")
        
        # 统计
        correct_count = sum(1 for s in samples if s.correct)
        total_reward = sum(s.reward for s in samples if s.reward is not None)
        avg_reward = total_reward / len(samples) if samples else 0
        
        print(f"正确数: {correct_count}")
        print(f"准确率: {correct_count / len(samples) * 100:.2f}%")
        print(f"平均奖励: {avg_reward:.4f}")
        print(f"总奖励: {total_reward:.4f}")
        
        # 按stage统计
        stages = {}
        for s in samples:
            stages[s.stage] = stages.get(s.stage, 0) + 1
        print(f"\n按阶段统计:")
        for stage, count in stages.items():
            print(f"  {stage}: {count}")
        
        # 查看前10个样本
        print(f"\n前10个样本详情:")
        print("-" * 80)
        for i, sample in enumerate(samples[:10], 1):
            seed = sample.meta.get('game_seed') if sample.meta else 'N/A'
            score = sample.meta.get('score') if sample.meta else 'N/A'
            success = sample.meta.get('success') if sample.meta else 'N/A'
            
            print(f"{i:2d}. Seed={seed:3s} | Correct={str(sample.correct):5s} | "
                  f"Reward={sample.reward:.3f} | Score={score} | Success={success}")
        
        # 查看错误的样本
        wrong_samples = [s for s in samples if not s.correct]
        print(f"\n错误样本数: {len(wrong_samples)}")
        if wrong_samples and len(wrong_samples) <= 5:
            print("错误样本详情:")
            for i, sample in enumerate(wrong_samples[:5], 1):
                print(f"\n  错误样本 {i}:")
                print(f"    seed: {sample.meta.get('game_seed') if sample.meta else 'N/A'}")
                print(f"    correct: {sample.correct}")
                print(f"    reward: {sample.reward}")
                print(f"    response: {sample.response[:100] if sample.response else 'None'}...")
                if sample.meta:
                    print(f"    action: {sample.meta.get('action')}")
                    print(f"    success: {sample.meta.get('success')}")
        
        # 查看正确的样本
        correct_samples = [s for s in samples if s.correct]
        print(f"\n正确样本数: {len(correct_samples)}")
        if correct_samples and len(correct_samples) <= 5:
            print("正确样本详情:")
            for i, sample in enumerate(correct_samples[:5], 1):
                print(f"\n  正确样本 {i}:")
                print(f"    seed: {sample.meta.get('game_seed') if sample.meta else 'N/A'}")
                print(f"    correct: {sample.correct}")
                print(f"    reward: {sample.reward}")
                print(f"    response: {sample.response[:100] if sample.response else 'None'}...")
                if sample.meta:
                    print(f"    action: {sample.meta.get('action')}")
                    print(f"    success: {sample.meta.get('success')}")
    
    print("\n" + "=" * 80 + "\n")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="分析Word Puzzle评估结果")
    parser.add_argument("--exp_id", type=str, default="word_puzzle_baseline_eval",
                       help="实验ID")
    args = parser.parse_args()
    
    analyze_results(args.exp_id)

















