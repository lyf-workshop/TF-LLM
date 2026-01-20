#!/usr/bin/env python3
"""
获取训练前后的详细统计信息

用法:
    python scripts/get_training_statistics.py --baseline_exp_id <baseline_id> --practice_exp_id <practice_id>
"""

import sys
from pathlib import Path
from sqlmodel import select, func
from collections import defaultdict

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.db.eval_datapoint import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def calculate_pass_at_k(samples, k):
    """计算 Pass@K"""
    problem_to_samples = defaultdict(list)
    for sample in samples:
        key = sample.raw_question or sample.question
        problem_to_samples[key].append(sample)
    
    solved_problems = 0
    for problem, problem_samples in problem_to_samples.items():
        # 取前k个样本
        samples_k = problem_samples[:k]
        # 如果任意一个正确，则问题被解决
        if any(s.reward and s.reward > 0.5 for s in samples_k):
            solved_problems += 1
    
    return solved_problems / len(problem_to_samples) if problem_to_samples else 0.0


def get_statistics(baseline_exp_id: str, practice_exp_id: str):
    """获取训练前后的详细统计"""
    
    print("\n" + "=" * 80)
    print("📊 训练前后详细统计")
    print("=" * 80)
    print(f"\nBaseline 实验: {baseline_exp_id}")
    print(f"Practice 实验: {practice_exp_id}")
    print()
    
    with SQLModelUtils.create_session() as session:
        # 获取 baseline 数据
        baseline_samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == baseline_exp_id
            )
        ))
        
        # 获取 practice 数据
        practice_samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == practice_exp_id
            )
        ))
        
        if not baseline_samples:
            print(f"❌ 未找到 Baseline 数据")
            return
        
        if not practice_samples:
            print(f"❌ 未找到 Practice 数据")
            return
        
        # Baseline 统计
        print("=" * 80)
        print("📈 Baseline (训练前) 统计")
        print("=" * 80)
        
        baseline_total = len(baseline_samples)
        baseline_correct = sum(1 for s in baseline_samples if s.reward and s.reward > 0.5)
        baseline_accuracy = baseline_correct / baseline_total if baseline_total > 0 else 0.0
        
        # 按问题分组
        baseline_problems = defaultdict(list)
        for sample in baseline_samples:
            key = sample.raw_question or sample.question
            baseline_problems[key].append(sample)
        
        baseline_solved_problems = sum(
            1 for problem_samples in baseline_problems.values()
            if any(s.reward and s.reward > 0.5 for s in problem_samples)
        )
        baseline_total_problems = len(baseline_problems)
        
        baseline_pass_at_32 = calculate_pass_at_k(baseline_samples, 32)
        
        print(f"\n样本级别统计:")
        print(f"  - 总样本数: {baseline_total}")
        print(f"  - 正确样本数: {baseline_correct}")
        print(f"  - 错误样本数: {baseline_total - baseline_correct}")
        print(f"  - 准确率: {baseline_accuracy:.2%}")
        
        print(f"\n问题级别统计:")
        print(f"  - 总问题数: {baseline_total_problems}")
        print(f"  - 已解决问题数: {baseline_solved_problems}")
        print(f"  - 未解决问题数: {baseline_total_problems - baseline_solved_problems}")
        print(f"  - 每题平均样本数: {baseline_total / baseline_total_problems:.1f}")
        print(f"  - Pass@32: {baseline_pass_at_32:.2%}")
        
        # Practice 统计
        print("\n" + "=" * 80)
        print("📈 Practice (训练后) 统计")
        print("=" * 80)
        
        practice_total = len(practice_samples)
        practice_correct = sum(1 for s in practice_samples if s.reward and s.reward > 0.5)
        practice_accuracy = practice_correct / practice_total if practice_total > 0 else 0.0
        
        # 按问题分组
        practice_problems = defaultdict(list)
        for sample in practice_samples:
            key = sample.raw_question or sample.question
            practice_problems[key].append(sample)
        
        practice_solved_problems = sum(
            1 for problem_samples in practice_problems.values()
            if any(s.reward and s.reward > 0.5 for s in problem_samples)
        )
        practice_total_problems = len(practice_problems)
        
        practice_pass_at_32 = calculate_pass_at_k(practice_samples, 32)
        
        print(f"\n样本级别统计:")
        print(f"  - 总样本数: {practice_total}")
        print(f"  - 正确样本数: {practice_correct}")
        print(f"  - 错误样本数: {practice_total - practice_correct}")
        print(f"  - 准确率: {practice_accuracy:.2%}")
        
        print(f"\n问题级别统计:")
        print(f"  - 总问题数: {practice_total_problems}")
        print(f"  - 已解决问题数: {practice_solved_problems}")
        print(f"  - 未解决问题数: {practice_total_problems - practice_solved_problems}")
        print(f"  - 每题平均样本数: {practice_total / practice_total_problems:.1f}")
        print(f"  - Pass@32: {practice_pass_at_32:.2%}")
        
        # 对比
        print("\n" + "=" * 80)
        print("📊 对比分析")
        print("=" * 80)
        
        accuracy_improvement = practice_accuracy - baseline_accuracy
        pass_at_32_improvement = practice_pass_at_32 - baseline_pass_at_32
        solved_improvement = practice_solved_problems - baseline_solved_problems
        
        print(f"\n样本级别对比:")
        print(f"  - 准确率: {baseline_accuracy:.2%} → {practice_accuracy:.2%} ({accuracy_improvement:+.2%})")
        print(f"  - 正确样本: {baseline_correct}/{baseline_total} → {practice_correct}/{practice_total}")
        
        print(f"\n问题级别对比:")
        print(f"  - Pass@32: {baseline_pass_at_32:.2%} → {practice_pass_at_32:.2%} ({pass_at_32_improvement:+.2%})")
        print(f"  - 已解决问题: {baseline_solved_problems}/{baseline_total_problems} → {practice_solved_problems}/{practice_total_problems} ({solved_improvement:+d})")
        
        # 变化分析
        print(f"\n变化分析:")
        if accuracy_improvement > 0:
            print(f"  ✅ 样本准确率提升了 {accuracy_improvement:.2%}")
        elif accuracy_improvement < 0:
            print(f"  ❌ 样本准确率下降了 {abs(accuracy_improvement):.2%}")
        else:
            print(f"  ➡️ 样本准确率保持不变")
        
        if pass_at_32_improvement > 0:
            print(f"  ✅ Pass@32 提升了 {pass_at_32_improvement:.2%}")
        elif pass_at_32_improvement < 0:
            print(f"  ❌ Pass@32 下降了 {abs(pass_at_32_improvement):.2%}")
        else:
            print(f"  ➡️ Pass@32 保持不变")
        
        if solved_improvement > 0:
            print(f"  ✅ 多解决了 {solved_improvement} 个问题")
        elif solved_improvement < 0:
            print(f"  ❌ 少解决了 {abs(solved_improvement)} 个问题")
        else:
            print(f"  ➡️ 解决的问题数量相同")
        
        print("\n" + "=" * 80)
        print()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="获取训练前后的详细统计信息"
    )
    parser.add_argument(
        "--baseline_exp_id",
        type=str,
        default="logic_zebralogic_test_eval",
        help="Baseline 实验 ID"
    )
    parser.add_argument(
        "--practice_exp_id",
        type=str,
        default="logic_practice_zebralogic_test_eval",
        help="Practice 实验 ID"
    )
    
    args = parser.parse_args()
    
    get_statistics(args.baseline_exp_id, args.practice_exp_id)


if __name__ == "__main__":
    main()


