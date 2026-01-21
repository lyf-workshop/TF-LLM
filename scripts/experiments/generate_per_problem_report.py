#!/usr/bin/env python3
"""
生成每个题目的正确答案数统计报告
"""

import sys
from pathlib import Path
from sqlmodel import select
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.db.eval_datapoint import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def generate_report(exp_id: str, output_file: str):
    """生成每个题目的统计报告"""
    
    print(f"\n生成报告: {exp_id} -> {output_file}\n")
    
    with SQLModelUtils.create_session() as session:
        samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == exp_id
            ).order_by(EvaluationSample.dataset_index)
        ))
        
        if not samples:
            print(f"未找到数据")
            return
        
        # 按问题分组
        problem_to_samples = defaultdict(list)
        for sample in samples:
            key = sample.raw_question or sample.question
            problem_to_samples[key].append(sample)
        
        # 生成报告
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"# 每个题目的正确答案数统计报告\n\n")
            f.write(f"**实验 ID**: `{exp_id}`\n\n")
            f.write("---\n\n")
            
            # 总体统计
            total_samples = len(samples)
            total_correct = sum(1 for s in samples if s.reward and s.reward > 0.5)
            total_problems = len(problem_to_samples)
            
            f.write("## 总体统计\n\n")
            f.write(f"- **总样本数**: {total_samples}\n")
            f.write(f"- **总问题数**: {total_problems}\n")
            f.write(f"- **总正确答案数**: {total_correct}\n")
            f.write(f"- **总错误答案数**: {total_samples - total_correct}\n")
            f.write(f"- **总体正确率**: {total_correct / total_samples * 100:.2f}%\n\n")
            f.write("---\n\n")
            
            # 每个题目的详细统计
            f.write("## 每个题目的详细统计\n\n")
            f.write("| 题目编号 | 总答案数 | 正确答案数 | 错误答案数 | 正确率 |\n")
            f.write("|---------|---------|-----------|-----------|--------|\n")
            
            results = []
            for problem, problem_samples in sorted(problem_to_samples.items()):
                correct_count = sum(1 for s in problem_samples if s.reward and s.reward > 0.5)
                total_count = len(problem_samples)
                correct_rate = correct_count / total_count * 100 if total_count > 0 else 0.0
                
                results.append({
                    'problem': problem,
                    'total': total_count,
                    'correct': correct_count,
                    'wrong': total_count - correct_count,
                    'correct_rate': correct_rate,
                    'samples': problem_samples
                })
                
                f.write(f"| {len(results)} | {total_count} | {correct_count} | "
                       f"{total_count - correct_count} | {correct_rate:.2f}% |\n")
            
            f.write("\n---\n\n")
            
            # 每个题目的详细信息
            f.write("## 每个题目的详细信息\n\n")
            
            for i, result in enumerate(results, 1):
                f.write(f"### 题目 {i}\n\n")
                
                # 问题内容
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
                f.write(f"- 正确率: {result['correct_rate']:.2f}%\n\n")
                
                # 正确答案的rollout编号
                if result['correct'] > 0:
                    correct_rollouts = []
                    for idx, sample in enumerate(result['samples'], 1):
                        if sample.reward and sample.reward > 0.5:
                            correct_rollouts.append(str(idx))
                    f.write(f"**正确答案的 Rollout 编号**: {', '.join(correct_rollouts)}\n\n")
                else:
                    f.write("**正确答案的 Rollout 编号**: 无\n\n")
                
                # 所有rollouts的reward列表
                f.write("**所有 Rollouts 的 Reward**:\n")
                f.write("```\n")
                for idx, sample in enumerate(result['samples'], 1):
                    if sample.reward is not None:
                        reward_str = f"{sample.reward:.1f}"
                        status = "✓" if sample.reward > 0.5 else "✗"
                    else:
                        reward_str = "N/A"
                        status = "✗"
                    f.write(f"Rollout {idx:2d}: {reward_str:>4s} {status}\n")
                f.write("```\n\n")
                
                f.write("---\n\n")
            
            # 按正确答案数排序
            f.write("## 按正确答案数排序\n\n")
            f.write("| 题目编号 | 正确答案数 | 错误答案数 | 正确率 |\n")
            f.write("|---------|-----------|-----------|--------|\n")
            
            sorted_results = sorted(results, key=lambda x: x['correct'], reverse=True)
            for result in sorted_results:
                original_idx = results.index(result) + 1
                f.write(f"| {original_idx} | {result['correct']} | {result['wrong']} | "
                       f"{result['correct_rate']:.2f}% |\n")
            
            f.write("\n---\n\n")
            
            # 分布统计
            f.write("## 正确答案数分布\n\n")
            distribution = defaultdict(int)
            for result in results:
                distribution[result['correct']] += 1
            
            f.write("| 正确答案数 | 题目数量 |\n")
            f.write("|-----------|---------|\n")
            for correct_count in sorted(distribution.keys(), reverse=True):
                problem_count = distribution[correct_count]
                f.write(f"| {correct_count} | {problem_count} |\n")
        
        print(f"报告已生成: {output_file}")
        print(f"总问题数: {total_problems}")
        print(f"总样本数: {total_samples}")
        print(f"总正确答案数: {total_correct}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true", help="生成 baseline 报告")
    parser.add_argument("--practice", action="store_true", help="生成 practice 报告")
    parser.add_argument("--exp_id", type=str, help="实验 ID")
    parser.add_argument("--output", type=str, help="输出文件")
    
    args = parser.parse_args()
    
    if args.exp_id:
        output = args.output or f"{args.exp_id}_每题统计.md"
        generate_report(args.exp_id, output)
    elif args.baseline:
        generate_report("logic_zebralogic_test_eval", "baseline_每题正确答案数统计.md")
    elif args.practice:
        generate_report("logic_practice_zebralogic_test_eval", "practice_每题正确答案数统计.md")
    else:
        print("生成 Baseline 报告...")
        generate_report("logic_zebralogic_test_eval", "baseline_每题正确答案数统计.md")
        print("\n生成 Practice 报告...")
        generate_report("logic_practice_zebralogic_test_eval", "practice_每题正确答案数统计.md")

