#!/usr/bin/env python3
"""
查看KORGym游戏的评估结果 - 符合论文标准
View KORGym evaluation results following paper standards

KORGym游戏的评分机制：
1. Word Puzzle (8-word_puzzle):
   - 评分 = 答对的单词数 / 总单词数
   - 例如：5个单词答对3个 = 0.6分
   - Success = score > 0

2. Alphabetical Sorting (22-alphabetical_sorting):
   - 评分 = 0或1 (全对或全错)
   - Success = score > 0

3. Wordle (33-wordle):
   - 评分 = 0或1 (猜中或失败)
   - Success = score == 1

论文中使用的评价指标：
- Accuracy: 成功率 (success_count / total_count)
- Average Score: 平均得分 (sum(scores) / total_count)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.utils import SQLModelUtils, get_logger
from utu.db import EvaluationSample
from sqlmodel import select, func
from typing import List, Dict
import json

logger = get_logger(__name__)


def analyze_korgym_results(exp_id: str, show_details: bool = False) -> Dict:
    """
    分析KORGym评估结果
    
    Args:
        exp_id: 实验ID
        show_details: 是否显示详细信息
    
    Returns:
        统计结果字典
    """
    with SQLModelUtils.create_session() as session:
        # 获取所有样本
        samples = session.exec(
            select(EvaluationSample).where(
            EvaluationSample.exp_id == exp_id
            ).order_by(EvaluationSample.id)
            ).all()
        
        if not samples:
            print(f"\n❌ 未找到实验结果: {exp_id}\n")
            return {}
        
        # 统计
        total = len(samples)
        correct_count = sum(1 for s in samples if s.correct)
        total_score = sum(s.reward for s in samples if s.reward is not None)
        avg_score = total_score / total if total > 0 else 0
        accuracy = correct_count / total * 100 if total > 0 else 0
        
        # 游戏信息（从第一个样本获取）
        game_name = samples[0].meta.get('game_name', 'Unknown') if samples[0].meta else 'Unknown'
        
        # 统计结果
        stats = {
            'exp_id': exp_id,
            'game_name': game_name,
            'total_samples': total,
            'correct_count': correct_count,
            'accuracy': accuracy,
            'avg_score': avg_score,
            'total_score': total_score
        }
        
        # 打印结果
        print(f"\n{'='*80}")
        print(f"实验结果: {exp_id}")
        print(f"{'='*80}")
        print(f"游戏: {game_name}")
        print(f"总样本数: {total}")
        print(f"成功数: {correct_count}")
        print(f"准确率 (Accuracy): {accuracy:.2f}%")
        print(f"平均得分 (Avg Score): {avg_score:.4f}")
        print(f"总得分 (Total Score): {total_score:.2f}")
        
        # 得分分布
        score_distribution = {}
        for s in samples:
            score_key = f"{s.reward:.2f}" if s.reward is not None else "0.00"
            score_distribution[score_key] = score_distribution.get(score_key, 0) + 1
        
        print(f"\n得分分布:")
        for score in sorted(score_distribution.keys(), key=float):
            count = score_distribution[score]
            percentage = count / total * 100
            print(f"  {score}: {count:3d} ({percentage:5.1f}%)")
        
        if show_details:
            print(f"\n{'='*80}")
            print(f"详细样本信息 (前10个)")
            print(f"{'='*80}")
            for i, sample in enumerate(samples[:10], 1):
                seed = sample.meta.get('game_seed') if sample.meta else 'N/A'
                score = sample.reward if sample.reward is not None else 0
                action = sample.meta.get('action') if sample.meta else 'N/A'
                
                print(f"\n样本 {i}:")
                print(f"  Seed: {seed}")
                print(f"  Correct: {sample.correct}")
                print(f"  Score: {score:.4f}")
                print(f"  Action: {str(action)[:60]}...")
        
        print(f"\n{'='*80}\n")
        
        return stats


def compare_results(baseline_exp_id: str, practice_exp_id: str):
    """
    对比基线和训练后的结果
    
    Args:
        baseline_exp_id: 基线实验ID
        practice_exp_id: 训练后实验ID
    """
    print("\n" + "="*80)
    print("对比分析: 基线 vs 训练后")
    print("="*80)
    
    baseline_stats = analyze_korgym_results(baseline_exp_id, show_details=False)
    practice_stats = analyze_korgym_results(practice_exp_id, show_details=False)
    
    if not baseline_stats or not practice_stats:
        return
    
    # 计算提升
    acc_improvement = practice_stats['accuracy'] - baseline_stats['accuracy']
    score_improvement = practice_stats['avg_score'] - baseline_stats['avg_score']
    
    print("\n" + "="*80)
    print("提升统计")
    print("="*80)
    print(f"准确率提升: {acc_improvement:+.2f}% (从 {baseline_stats['accuracy']:.2f}% 到 {practice_stats['accuracy']:.2f}%)")
    print(f"平均得分提升: {score_improvement:+.4f} (从 {baseline_stats['avg_score']:.4f} 到 {practice_stats['avg_score']:.4f})")
    
    if acc_improvement > 0:
        print(f"\n✅ 训练有效！准确率提升了 {acc_improvement:.2f}%")
    elif acc_improvement < 0:
        print(f"\n⚠️  训练后准确率下降了 {abs(acc_improvement):.2f}%")
    else:
        print(f"\n➖ 准确率没有变化")
    
    print("="*80 + "\n")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="查看KORGym游戏的评估结果",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--exp_id", "-e",
        type=str,
        help="实验ID (例如: word_puzzle_baseline_eval)"
    )
    
    parser.add_argument(
        "--compare", "-c",
        nargs=2,
        metavar=("BASELINE", "PRACTICE"),
        help="对比两个实验 (例如: --compare word_puzzle_baseline_eval word_puzzle_practice_eval)"
    )
    
    parser.add_argument(
        "--detailed", "-d",
        action="store_true",
        help="显示详细信息"
    )
    
    parser.add_argument(
        "--game",
        choices=["word_puzzle", "alphabetical_sorting", "wordle", "all"],
        help="快速查看指定游戏的结果"
    )
    
    args = parser.parse_args()
    
    # 如果没有任何参数，显示帮助
    if not any([args.exp_id, args.compare, args.game]):
        parser.print_help()
        return
    
    # 快速查看游戏结果
    if args.game:
        if args.game == "all" or args.game == "word_puzzle":
            compare_results("word_puzzle_baseline_eval", "word_puzzle_practice_eval")
        if args.game == "all" or args.game == "alphabetical_sorting":
            compare_results("alphabetical_sorting_baseline_eval", "alphabetical_sorting_practice_eval")
        if args.game == "all" or args.game == "wordle":
            compare_results("wordle_baseline_eval", "wordle_practice_eval")
        return
    
    # 对比模式
    if args.compare:
        compare_results(args.compare[0], args.compare[1])
        return
    
    # 单个实验查看
    if args.exp_id:
        analyze_korgym_results(args.exp_id, show_details=args.detailed)


if __name__ == "__main__":
    main()
