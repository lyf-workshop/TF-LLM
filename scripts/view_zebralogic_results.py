"""
查看 ZebraLogic 实验的评估结果
View ZebraLogic experiment evaluation results

用法 / Usage:
    python scripts/view_zebralogic_results.py
"""

import sys
from pathlib import Path
from sqlmodel import select
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.db import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def calculate_pass_at_k(samples, k=None):
    """计算 Pass@K 指标"""
    problem_to_scores = defaultdict(list)
    
    for sample in samples:
        reward = sample.reward if sample.reward is not None else 0.0
        problem_to_scores[sample.raw_question].append(reward)
    
    if not problem_to_scores:
        return 0.0, 0, 0
    
    # 如果未指定 k，使用最大的 k
    if k is None:
        k = max(len(scores) for scores in problem_to_scores.values())
    
    problem_to_max_score = {
        problem: max((s for s in scores if s is not None), default=0.0) 
        for problem, scores in problem_to_scores.items()
    }
    
    pass_k = sum(max_reward for max_reward in problem_to_max_score.values()) / len(problem_to_max_score)
    total_problems = len(problem_to_max_score)
    solved_problems = sum(1 for score in problem_to_max_score.values() if score > 0)
    
    return pass_k, solved_problems, total_problems


def calculate_accuracy(samples):
    """计算准确率"""
    if not samples:
        return 0.0, 0, 0
    
    correct = sum(1 for s in samples if s.reward and s.reward > 0)
    total = len(samples)
    accuracy = correct / total if total > 0 else 0.0
    
    return accuracy, correct, total


def view_experiment_results(exp_id):
    """查看特定实验的结果"""
    with SQLModelUtils.create_session() as session:
        samples = session.exec(
            select(EvaluationSample).where(EvaluationSample.exp_id == exp_id)
        ).all()
        
        if not samples:
            print(f"❌ 未找到实验 '{exp_id}' 的评估结果")
            print(f"\n请先运行评估:")
            print(f"  uv run python scripts/run_eval.py --config eval/logic/logic_zebralogic_test.yaml")
            return None
        
        # 计算指标
        pass_k, solved, total_problems = calculate_pass_at_k(samples)
        accuracy, correct, total_samples = calculate_accuracy(samples)
        
        # 显示结果
        print(f"\n{'=' * 70}")
        print(f"实验 ID: {exp_id}")
        print(f"{'=' * 70}")
        
        print(f"\n📊 总体统计:")
        print(f"  总样本数: {total_samples}")
        print(f"  总问题数: {total_problems}")
        print(f"  每题采样数: {total_samples // total_problems if total_problems > 0 else 0}")
        
        print(f"\n✅ Pass@K 指标:")
        k = total_samples // total_problems if total_problems > 0 else 1
        print(f"  Pass@{k}: {pass_k:.4f} ({pass_k*100:.2f}%)")
        print(f"  已解决问题: {solved}/{total_problems}")
        
        print(f"\n📈 准确率:")
        print(f"  Accuracy: {accuracy:.4f} ({accuracy*100:.2f}%)")
        print(f"  正确样本: {correct}/{total_samples}")
        
        # 按问题统计
        print(f"\n📝 按问题统计:")
        problem_to_samples = defaultdict(list)
        for sample in samples:
            problem_to_samples[sample.raw_question].append(sample)
        
        solved_problems_list = []
        unsolved_problems_list = []
        
        for problem, prob_samples in problem_to_samples.items():
            max_reward = max((s.reward for s in prob_samples if s.reward is not None), default=0.0)
            if max_reward > 0:
                solved_problems_list.append((problem[:80], max_reward))
            else:
                unsolved_problems_list.append(problem[:80])
        
        if solved_problems_list:
            print(f"\n  ✓ 已解决 ({len(solved_problems_list)} 个):")
            for i, (problem, reward) in enumerate(solved_problems_list[:5], 1):
                print(f"    {i}. {problem}... (reward: {reward})")
            if len(solved_problems_list) > 5:
                print(f"    ... 还有 {len(solved_problems_list) - 5} 个问题")
        
        if unsolved_problems_list:
            print(f"\n  ✗ 未解决 ({len(unsolved_problems_list)} 个):")
            for i, problem in enumerate(unsolved_problems_list[:5], 1):
                print(f"    {i}. {problem}...")
            if len(unsolved_problems_list) > 5:
                print(f"    ... 还有 {len(unsolved_problems_list) - 5} 个问题")
        
        print(f"\n{'=' * 70}\n")
        
        return {
            'exp_id': exp_id,
            'pass_k': pass_k,
            'accuracy': accuracy,
            'solved': solved,
            'total_problems': total_problems,
            'correct': correct,
            'total_samples': total_samples,
        }


def compare_baseline_and_practice():
    """比较 baseline 和 practice 的结果"""
    baseline_exp_id = "logic_zebralogic_test_eval"
    practice_exp_id = "logic_practice_zebralogic_test_eval"
    
    print("\n" + "=" * 70)
    print("ZebraLogic 实验结果对比")
    print("Baseline vs Practice Comparison")
    print("=" * 70)
    
    baseline_results = view_experiment_results(baseline_exp_id)
    practice_results = view_experiment_results(practice_exp_id)
    
    if baseline_results and practice_results:
        print("\n" + "=" * 70)
        print("📊 对比总结")
        print("=" * 70)
        
        baseline_pass = baseline_results['pass_k']
        practice_pass = practice_results['pass_k']
        improvement = practice_pass - baseline_pass
        improvement_pct = (improvement / baseline_pass * 100) if baseline_pass > 0 else 0
        
        print(f"\nPass@K 对比:")
        print(f"  Baseline:  {baseline_pass:.4f} ({baseline_pass*100:.2f}%)")
        print(f"  Practice:  {practice_pass:.4f} ({practice_pass*100:.2f}%)")
        print(f"  提升:      {improvement:+.4f} ({improvement_pct:+.2f}%)")
        
        baseline_acc = baseline_results['accuracy']
        practice_acc = practice_results['accuracy']
        acc_improvement = practice_acc - baseline_acc
        acc_improvement_pct = (acc_improvement / baseline_acc * 100) if baseline_acc > 0 else 0
        
        print(f"\n准确率对比:")
        print(f"  Baseline:  {baseline_acc:.4f} ({baseline_acc*100:.2f}%)")
        print(f"  Practice:  {practice_acc:.4f} ({practice_acc*100:.2f}%)")
        print(f"  提升:      {acc_improvement:+.4f} ({acc_improvement_pct:+.2f}%)")
        
        baseline_solved = baseline_results['solved']
        practice_solved = practice_results['solved']
        total = baseline_results['total_problems']
        
        print(f"\n解决问题数对比:")
        print(f"  Baseline:  {baseline_solved}/{total}")
        print(f"  Practice:  {practice_solved}/{total}")
        print(f"  新增解决:  {practice_solved - baseline_solved} 个问题")
        
        print(f"\n{'=' * 70}\n")


def list_all_experiments():
    """列出所有评估实验"""
    with SQLModelUtils.create_session() as session:
        exp_ids = session.exec(
            select(EvaluationSample.exp_id).distinct()
        ).all()
        
        print("\n" + "=" * 70)
        print("所有评估实验")
        print("=" * 70)
        
        if exp_ids:
            for exp_id in sorted(exp_ids):
                count = session.exec(
                    select(EvaluationSample).where(EvaluationSample.exp_id == exp_id)
                ).all()
                print(f"  - {exp_id} ({len(count)} samples)")
        else:
            print("  (无评估实验)")
        
        print("=" * 70 + "\n")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="查看 ZebraLogic 实验评估结果")
    parser.add_argument(
        "--exp_id",
        type=str,
        help="查看特定实验的结果（默认: logic_zebralogic_test_eval）",
        default="logic_zebralogic_test_eval"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="比较 baseline 和 practice 的结果"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有实验"
    )
    
    args = parser.parse_args()
    
    if args.list:
        list_all_experiments()
    elif args.compare:
        compare_baseline_and_practice()
    else:
        view_experiment_results(args.exp_id)


if __name__ == "__main__":
    main()

