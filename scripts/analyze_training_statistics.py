#!/usr/bin/env python3
"""
分析训练前后的详细统计信息

用法:
    python scripts/analyze_training_statistics.py --baseline_exp_id <baseline_id> --practice_exp_id <practice_id>
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


def analyze_statistics(baseline_exp_id: str, practice_exp_id: str):
    """分析训练前后的详细统计"""
    
    print("\n" + "=" * 80)
    print("📊 训练前后详细统计分析")
    print("=" * 80)
    print(f"\nBaseline 实验: {baseline_exp_id}")
    print(f"Practice 实验: {practice_exp_id}")
    print()
    
    with SQLModelUtils.create_session() as session:
        # 获取 baseline 结果
        print("📈 Baseline 统计:")
        print("-" * 80)
        baseline_samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == baseline_exp_id
            )
        ))
        
        if not baseline_samples:
            print(f"❌ 未找到 Baseline 数据")
            return
        
        # Baseline 统计
        baseline_total = len(baseline_samples)
        baseline_correct = sum(1 for s in baseline_samples if s.reward and s.reward > 0.5)
        baseline_accuracy = baseline_correct / baseline_total if baseline_total > 0 else 0.0
        
        # 按问题分组
        baseline_problems = defaultdict(list)
        for sample in baseline_samples:
            key = sample.raw_question or sample.question
            baseline_problems[key].append(sample)
        
        baseline_total_problems = len(baseline_problems)
        baseline_solved_problems = sum(
            1 for problem_samples in baseline_problems.values()
            if any(s.reward and s.reward > 0.5 for s in problem_samples)
        )
        
        # Pass@K
        baseline_pass_at_32 = calculate_pass_at_k(baseline_samples, 32)
        
        print(f"  总样本数: {baseline_total}")
        print(f"  正确样本数: {baseline_correct}")
        print(f"  准确率 (样本级别): {baseline_accuracy:.2%} ({baseline_correct}/{baseline_total})")
        print(f"  总问题数: {baseline_total_problems}")
        print(f"  已解决问题数: {baseline_solved_problems}")
        print(f"  问题解决率: {baseline_solved_problems/baseline_total_problems:.2%} ({baseline_solved_problems}/{baseline_total_problems})")
        print(f"  Pass@32: {baseline_pass_at_32:.2%}")
        
        # 获取 practice 结果
        print("\n📈 Practice 统计:")
        print("-" * 80)
        practice_samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == practice_exp_id
            )
        ))
        
        if not practice_samples:
            print(f"❌ 未找到 Practice 数据")
            return
        
        # Practice 统计
        practice_total = len(practice_samples)
        practice_correct = sum(1 for s in practice_samples if s.reward and s.reward > 0.5)
        practice_accuracy = practice_correct / practice_total if practice_total > 0 else 0.0
        
        # 按问题分组
        practice_problems = defaultdict(list)
        for sample in practice_samples:
            key = sample.raw_question or sample.question
            practice_problems[key].append(sample)
        
        practice_total_problems = len(practice_problems)
        practice_solved_problems = sum(
            1 for problem_samples in practice_problems.values()
            if any(s.reward and s.reward > 0.5 for s in problem_samples)
        )
        
        # Pass@K
        practice_pass_at_32 = calculate_pass_at_k(practice_samples, 32)
        
        print(f"  总样本数: {practice_total}")
        print(f"  正确样本数: {practice_correct}")
        print(f"  准确率 (样本级别): {practice_accuracy:.2%} ({practice_correct}/{practice_total})")
        print(f"  总问题数: {practice_total_problems}")
        print(f"  已解决问题数: {practice_solved_problems}")
        print(f"  问题解决率: {practice_solved_problems/practice_total_problems:.2%} ({practice_solved_problems}/{practice_total_problems})")
        print(f"  Pass@32: {practice_pass_at_32:.2%}")
        
        # 对比分析
        print("\n📊 对比分析:")
        print("-" * 80)
        
        # 样本级别改进
        accuracy_improvement = practice_accuracy - baseline_accuracy
        print(f"  样本准确率变化: {baseline_accuracy:.2%} → {practice_accuracy:.2%} ({accuracy_improvement:+.2%})")
        print(f"  正确样本数变化: {baseline_correct} → {practice_correct} ({practice_correct - baseline_correct:+d})")
        
        # 问题级别改进
        problem_improvement = practice_solved_problems - baseline_solved_problems
        problem_improvement_rate = (practice_solved_problems / practice_total_problems) - (baseline_solved_problems / baseline_total_problems)
        print(f"  问题解决率变化: {baseline_solved_problems/baseline_total_problems:.2%} → {practice_solved_problems/practice_total_problems:.2%} ({problem_improvement_rate:+.2%})")
        print(f"  已解决问题数变化: {baseline_solved_problems} → {practice_solved_problems} ({problem_improvement:+d})")
        
        # Pass@32 改进
        pass_improvement = practice_pass_at_32 - baseline_pass_at_32
        print(f"  Pass@32 变化: {baseline_pass_at_32:.2%} → {practice_pass_at_32:.2%} ({pass_improvement:+.2%})")
        
        # 详细变化分析
        print("\n🔍 详细变化分析:")
        print("-" * 80)
        
        # 找出共同问题
        baseline_question_set = set(baseline_problems.keys())
        practice_question_set = set(practice_problems.keys())
        common_questions = baseline_question_set & practice_question_set
        
        improved = 0
        regressed = 0
        unchanged_correct = 0
        unchanged_incorrect = 0
        
        for question in common_questions:
            baseline_best = max((s.reward for s in baseline_problems[question] if s.reward is not None), default=0.0)
            practice_best = max((s.reward for s in practice_problems[question] if s.reward is not None), default=0.0)
            
            baseline_correct_q = baseline_best > 0.5
            practice_correct_q = practice_best > 0.5
            
            if not baseline_correct_q and practice_correct_q:
                improved += 1
            elif baseline_correct_q and not practice_correct_q:
                regressed += 1
            elif baseline_correct_q and practice_correct_q:
                unchanged_correct += 1
            else:
                unchanged_incorrect += 1
        
        print(f"  共同问题数: {len(common_questions)}")
        print(f"  ✅ 改进: {improved} 个（错误 → 正确）")
        print(f"  ❌ 退化: {regressed} 个（正确 → 错误）")
        print(f"  ➡️  保持正确: {unchanged_correct} 个")
        print(f"  ➡️  保持错误: {unchanged_incorrect} 个")
        
        # 总结
        print("\n" + "=" * 80)
        print("📝 总结")
        print("=" * 80)
        
        if accuracy_improvement > 0:
            print(f"✅ 训练有效：样本准确率提升了 {accuracy_improvement:.2%}")
        elif accuracy_improvement < 0:
            print(f"⚠️  训练可能有问题：样本准确率下降了 {abs(accuracy_improvement):.2%}")
        else:
            print("➡️  样本准确率没有变化")
        
        if problem_improvement > 0:
            print(f"✅ 问题解决率提升了 {problem_improvement_rate:.2%}，多解决了 {problem_improvement} 个问题")
        elif problem_improvement < 0:
            print(f"⚠️  问题解决率下降了 {abs(problem_improvement_rate):.2%}，少解决了 {abs(problem_improvement)} 个问题")
        else:
            print("➡️  问题解决率没有变化")
        
        if improved > regressed:
            print(f"✅ 净改进 {improved - regressed} 个问题")
        elif improved < regressed:
            print(f"⚠️  净退化 {regressed - improved} 个问题")
        else:
            print("➡️  改进和退化数量相同")
        
        print()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="分析训练前后的详细统计信息"
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
    
    analyze_statistics(args.baseline_exp_id, args.practice_exp_id)


if __name__ == "__main__":
    main()

