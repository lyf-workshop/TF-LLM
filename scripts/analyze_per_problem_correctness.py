#!/usr/bin/env python3
"""
统计每个题目的32个答案中的正确答案数

用法:
    python scripts/analyze_per_problem_correctness.py --exp_id <exp_id> --output <output_file>
"""

import sys
from pathlib import Path
from sqlmodel import select
from collections import defaultdict
import argparse

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.db.eval_datapoint import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def analyze_per_problem(exp_id: str, output_file: str = None):
    """分析每个题目的正确答案数"""
    
    print("\n" + "=" * 80)
    print("分析每个题目的正确答案数")
    print("=" * 80)
    print(f"\n实验 ID: {exp_id}")
    print()
    
    with SQLModelUtils.create_session() as session:
        # 获取所有样本
        samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == exp_id
            ).order_by(EvaluationSample.dataset_index)
        ))
        
        if not samples:
            print(f"[错误] 未找到数据 (exp_id: {exp_id})")
            return
        
        print(f"总样本数: {len(samples)}")
        
        # 按问题分组
        problem_to_samples = defaultdict(list)
        for sample in samples:
            key = sample.raw_question or sample.question
            problem_to_samples[key].append(sample)
        
        total_problems = len(problem_to_samples)
        print(f"总问题数: {total_problems}")
        print()
        
        # 统计每个问题的正确答案数
        results = []
        for problem, problem_samples in sorted(problem_to_samples.items(), key=lambda x: len(x[1])):
            # 统计正确答案数（reward > 0.5）
            correct_count = sum(1 for s in problem_samples if s.reward and s.reward > 0.5)
            total_count = len(problem_samples)
            correct_rate = correct_count / total_count * 100 if total_count > 0 else 0.0
            
            # 获取最佳reward
            rewards = [s.reward for s in problem_samples if s.reward is not None]
            best_reward = max(rewards) if rewards else 0.0
            
            results.append({
                'problem': problem,
                'total': total_count,
                'correct': correct_count,
                'wrong': total_count - correct_count,
                'correct_rate': correct_rate,
                'best_reward': best_reward,
                'samples': problem_samples
            })
        
        # 显示统计结果
        print("=" * 80)
        print("每个题目的正确答案数统计")
        print("=" * 80)
        print()
        print(f"{'题目编号':<8} {'总答案数':<10} {'正确答案数':<12} {'错误答案数':<12} {'正确率':<10} {'最佳Reward':<12}")
        print("-" * 80)
        
        for i, result in enumerate(results, 1):
            print(f"{i:<8} {result['total']:<10} {result['correct']:<12} {result['wrong']:<12} "
                  f"{result['correct_rate']:>6.2f}% {result['best_reward']:>10.2f}")
        
        # 总体统计
        total_samples = sum(r['total'] for r in results)
        total_correct = sum(r['correct'] for r in results)
        total_wrong = total_samples - total_correct
        overall_rate = total_correct / total_samples * 100 if total_samples > 0 else 0.0
        
        print("-" * 80)
        print(f"{'总计':<8} {total_samples:<10} {total_correct:<12} {total_wrong:<12} "
              f"{overall_rate:>6.2f}%")
        print()
        
        # 生成详细报告
        if output_file:
            generate_detailed_report(results, exp_id, output_file, total_samples, total_correct, overall_rate)
            print(f"\n详细报告已保存到: {output_file}")
        
        print("=" * 80)
        print()


def generate_detailed_report(results, exp_id, output_file, total_samples, total_correct, overall_rate):
    """生成详细的报告文件"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# 每个题目的正确答案数统计报告\n\n")
        f.write(f"**实验 ID**: `{exp_id}`\n\n")
        f.write("---\n\n")
        
        # 总体统计
        f.write("## 总体统计\n\n")
        f.write(f"- **总样本数**: {total_samples}\n")
        f.write(f"- **总问题数**: {len(results)}\n")
        f.write(f"- **总正确答案数**: {total_correct}\n")
        f.write(f"- **总错误答案数**: {total_samples - total_correct}\n")
        f.write(f"- **总体正确率**: {overall_rate:.2f}%\n\n")
        f.write("---\n\n")
        
        # 每个题目的详细统计
        f.write("## 每个题目的详细统计\n\n")
        
        for i, result in enumerate(results, 1):
            f.write(f"### 题目 {i}\n\n")
            
            # 问题内容（截断显示）
            problem_text = result['problem']
            if len(problem_text) > 500:
                f.write(f"**问题** (前500字符):\n```\n{problem_text[:500]}...\n```\n\n")
            else:
                f.write(f"**问题**:\n```\n{problem_text}\n```\n\n")
            
            # 统计信息
            f.write("**统计信息**:\n")
            f.write(f"- 总答案数: {result['total']}\n")
            f.write(f"- 正确答案数: {result['correct']}\n")
            f.write(f"- 错误答案数: {result['wrong']}\n")
            f.write(f"- 正确率: {result['correct_rate']:.2f}%\n")
            f.write(f"- 最佳 Reward: {result['best_reward']:.2f}\n\n")
            
            # 正确答案的rollout编号
            if result['correct'] > 0:
                correct_rollouts = []
                for idx, sample in enumerate(result['samples'], 1):
                    if sample.reward and sample.reward > 0.5:
                        correct_rollouts.append(str(idx))
                f.write(f"**正确答案的 Rollout 编号**: {', '.join(correct_rollouts)}\n\n")
            
            # 所有rollouts的reward列表
            f.write("**所有 Rollouts 的 Reward**:\n")
            f.write("```\n")
            for idx, sample in enumerate(result['samples'], 1):
                reward = sample.reward if sample.reward is not None else 'N/A'
                f.write(f"Rollout {idx:2d}: {reward}\n")
            f.write("```\n\n")
            
            f.write("---\n\n")
        
        # 按正确数排序的汇总
        f.write("## 按正确答案数排序\n\n")
        f.write("| 题目编号 | 正确答案数 | 错误答案数 | 正确率 | 最佳Reward |\n")
        f.write("|---------|-----------|-----------|--------|-----------|\n")
        
        sorted_results = sorted(results, key=lambda x: x['correct'], reverse=True)
        for i, result in enumerate(sorted_results, 1):
            original_idx = results.index(result) + 1
            f.write(f"| {original_idx} | {result['correct']} | {result['wrong']} | "
                   f"{result['correct_rate']:.2f}% | {result['best_reward']:.2f} |\n")
        
        f.write("\n---\n\n")
        
        # 问题分布统计
        f.write("## 问题分布统计\n\n")
        correct_distribution = defaultdict(int)
        for result in results:
            correct_distribution[result['correct']] += 1
        
        f.write("| 正确答案数 | 题目数量 |\n")
        f.write("|-----------|---------|\n")
        for correct_count in sorted(correct_distribution.keys(), reverse=True):
            problem_count = correct_distribution[correct_count]
            f.write(f"| {correct_count} | {problem_count} |\n")


def main():
    parser = argparse.ArgumentParser(
        description="统计每个题目的32个答案中的正确答案数"
    )
    parser.add_argument(
        "--exp_id",
        type=str,
        default="logic_zebralogic_test_eval",
        help="实验 ID"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出文件路径（可选）"
    )
    
    args = parser.parse_args()
    
    analyze_per_problem(args.exp_id, args.output)


if __name__ == "__main__":
    main()

















































































