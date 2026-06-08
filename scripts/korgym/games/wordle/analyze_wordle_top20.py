#!/usr/bin/env python3
"""
统计Wordle游戏前20题的得分情况
Analyze top 20 Wordle game scores

用法:
    uv run python scripts/analyze_wordle_top20.py --exp_id wordle_eval
    uv run python scripts/analyze_wordle_top20.py --exp_id wordle_practice_eval
    uv run python scripts/analyze_wordle_top20.py --exp_id wordle_eval --count 20
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.utils import SQLModelUtils, get_logger
from utu.db import EvaluationSample
from sqlmodel import select
from typing import List, Dict, Optional
import argparse

logger = get_logger(__name__)


def analyze_top_n_scores(exp_id: str, n: int = 20) -> Dict:
    """
    统计前N题的得分情况
    
    Args:
        exp_id: 实验ID
        n: 要统计的题目数量（默认20）
    
    Returns:
        统计结果字典
    """
    with SQLModelUtils.create_session() as session:
        # 获取前N个样本（按id排序，即按评估顺序）
        samples = session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == exp_id
            ).order_by(EvaluationSample.id).limit(n)
        ).all()
        
        if not samples:
            print(f"\n❌ 未找到实验结果: {exp_id}\n")
            print("💡 提示: 请确认实验ID是否正确，或先运行评估")
            return {}
        
        # 统计信息
        total = len(samples)
        correct_count = sum(1 for s in samples if s.correct)
        total_score = sum(s.reward for s in samples if s.reward is not None)
        avg_score = total_score / total if total > 0 else 0
        accuracy = correct_count / total * 100 if total > 0 else 0
        
        # 游戏信息
        game_name = samples[0].meta.get('game_name', 'Unknown') if samples[0].meta else 'Unknown'
        
        # 打印标题
        print(f"\n{'='*80}")
        print(f"Wordle 前 {total} 题得分统计")
        print(f"{'='*80}")
        print(f"实验ID: {exp_id}")
        print(f"游戏: {game_name}")
        print(f"{'='*80}\n")
        
        # 打印每题的详细信息
        print(f"{'题号':<6} {'Seed':<8} {'得分':<8} {'结果':<8} {'状态'}")
        print(f"{'-'*80}")
        
        for i, sample in enumerate(samples, 1):
            seed = sample.meta.get('game_seed', 'N/A') if sample.meta else 'N/A'
            score = sample.reward if sample.reward is not None else 0.0
            is_correct = sample.correct
            status = "✅ 成功" if is_correct else "❌ 失败"
            
            print(f"{i:<6} {str(seed):<8} {score:<8.4f} {'正确' if is_correct else '错误':<8} {status}")
        
        # 打印统计摘要
        print(f"\n{'='*80}")
        print(f"统计摘要")
        print(f"{'='*80}")
        print(f"总题数: {total}")
        print(f"成功数: {correct_count}")
        print(f"失败数: {total - correct_count}")
        print(f"准确率 (Accuracy): {accuracy:.2f}%")
        print(f"平均得分 (Avg Score): {avg_score:.4f}")
        print(f"总得分: {total_score:.2f}")
        
        # 得分分布
        score_1_count = sum(1 for s in samples if s.reward == 1.0)
        score_0_count = sum(1 for s in samples if s.reward == 0.0)
        
        print(f"\n得分分布:")
        print(f"  1.0分 (成功): {score_1_count:3d} 题 ({score_1_count/total*100:5.1f}%)")
        print(f"  0.0分 (失败): {score_0_count:3d} 题 ({score_0_count/total*100:5.1f}%)")
        
        # 连续成功/失败统计
        consecutive_success = 0
        consecutive_fail = 0
        max_consecutive_success = 0
        max_consecutive_fail = 0
        current_success_streak = 0
        current_fail_streak = 0
        
        for sample in samples:
            if sample.correct:
                current_success_streak += 1
                current_fail_streak = 0
                max_consecutive_success = max(max_consecutive_success, current_success_streak)
            else:
                current_fail_streak += 1
                current_success_streak = 0
                max_consecutive_fail = max(max_consecutive_fail, current_fail_streak)
        
        print(f"\n连续表现:")
        print(f"  最长连续成功: {max_consecutive_success} 题")
        print(f"  最长连续失败: {max_consecutive_fail} 题")
        
        # 前10题 vs 后10题对比（如果n>=20）
        if total >= 20:
            first_10 = samples[:10]
            last_10 = samples[10:20]
            
            first_10_correct = sum(1 for s in first_10 if s.correct)
            last_10_correct = sum(1 for s in last_10 if s.correct)
            first_10_acc = first_10_correct / 10 * 100
            last_10_acc = last_10_correct / 10 * 100
            
            print(f"\n前后对比 (前10题 vs 后10题):")
            print(f"  前10题准确率: {first_10_acc:.2f}% ({first_10_correct}/10)")
            print(f"  后10题准确率: {last_10_acc:.2f}% ({last_10_correct}/10)")
            
            if last_10_acc > first_10_acc:
                improvement = last_10_acc - first_10_acc
                print(f"  ✅ 后10题表现更好，提升了 {improvement:.2f}%")
            elif last_10_acc < first_10_acc:
                decline = first_10_acc - last_10_acc
                print(f"  ⚠️  后10题表现下降，降低了 {decline:.2f}%")
            else:
                print(f"  ➖ 前后表现一致")
        
        print(f"\n{'='*80}\n")
        
        return {
            'exp_id': exp_id,
            'game_name': game_name,
            'total': total,
            'correct_count': correct_count,
            'accuracy': accuracy,
            'avg_score': avg_score,
            'total_score': total_score,
            'samples': samples
        }


def main():
    parser = argparse.ArgumentParser(
        description="统计Wordle游戏前N题的得分情况",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--exp_id", "-e",
        type=str,
        required=True,
        help="实验ID (例如: wordle_eval, wordle_practice_eval)"
    )
    
    parser.add_argument(
        "--count", "-n",
        type=int,
        default=20,
        help="要统计的题目数量 (默认: 20)"
    )
    
    args = parser.parse_args()
    
    # 执行分析
    result = analyze_top_n_scores(args.exp_id, args.count)
    
    if not result:
        sys.exit(1)


if __name__ == "__main__":
    main()












