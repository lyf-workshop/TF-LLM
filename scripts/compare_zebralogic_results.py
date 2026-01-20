#!/usr/bin/env python3
"""比较 ZebraLogic baseline 和 enhanced agent 的结果"""

from sqlmodel import select
from collections import defaultdict

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


def compare_results():
    """比较 baseline 和 enhanced 结果"""
    
    exp_ids = {
        "baseline": "logic_zebralogic_test_eval",
        "enhanced": "logic_practice_zebralogic_test_eval"
    }
    
    print("\n" + "="*80)
    print("ZebraLogic Training-Free GRPO 效果对比")
    print("="*80 + "\n")
    
    with SQLModelUtils.create_session() as session:
        results = {}
        
        for label, exp_id in exp_ids.items():
            statement = select(EvaluationSample).where(
                EvaluationSample.exp_id == exp_id
            )
            samples = list(session.exec(statement))
            
            if not samples:
                print(f"⚠️  {label.upper()}: 未找到数据 (exp_id: {exp_id})")
                results[label] = None
                continue
            
            # 计算指标
            total_samples = len(samples)
            correct_samples = sum(1 for s in samples if s.reward and s.reward > 0.5)
            accuracy = correct_samples / total_samples if total_samples > 0 else 0.0
            
            # Pass@K (k=32)
            pass_at_32 = calculate_pass_at_k(samples, 32)
            
            # 按问题分组统计
            problem_to_samples = defaultdict(list)
            for sample in samples:
                key = sample.raw_question or sample.question
                problem_to_samples[key].append(sample)
            
            total_problems = len(problem_to_samples)
            solved_problems = sum(
                1 for problem_samples in problem_to_samples.values()
                if any(s.reward and s.reward > 0.5 for s in problem_samples)
            )
            
            # 统计每个问题的正确答案数
            per_problem_stats = []
            for problem, problem_samples in sorted(problem_to_samples.items()):
                correct_in_problem = sum(1 for s in problem_samples if s.reward and s.reward > 0.5)
                per_problem_stats.append({
                    'problem': problem,
                    'total': len(problem_samples),
                    'correct': correct_in_problem,
                    'wrong': len(problem_samples) - correct_in_problem
                })
            
            results[label] = {
                "total_samples": total_samples,
                "correct_samples": correct_samples,
                "accuracy": accuracy,
                "total_problems": total_problems,
                "solved_problems": solved_problems,
                "pass_at_32": pass_at_32,
                "per_problem_stats": per_problem_stats,
            }
        
        # 显示对比
        if results["baseline"] and results["enhanced"]:
            print("📊 性能对比:\n")
            print(f"{'指标':<20} {'Baseline':<20} {'Enhanced':<20} {'改进':<20}")
            print("-" * 80)
            
            # Accuracy
            baseline_acc = results["baseline"]["accuracy"]
            enhanced_acc = results["enhanced"]["accuracy"]
            acc_improvement = enhanced_acc - baseline_acc
            print(f"{'Accuracy':<20} {baseline_acc:>8.2%} ({results['baseline']['correct_samples']}/{results['baseline']['total_samples']:<8}) "
                  f"{enhanced_acc:>8.2%} ({results['enhanced']['correct_samples']}/{results['enhanced']['total_samples']:<8}) "
                  f"{acc_improvement:>+8.2%}")
            
            # Pass@32
            baseline_pass = results["baseline"]["pass_at_32"]
            enhanced_pass = results["enhanced"]["pass_at_32"]
            pass_improvement = enhanced_pass - baseline_pass
            print(f"{'Pass@32':<20} {baseline_pass:>8.2%} ({results['baseline']['solved_problems']}/{results['baseline']['total_problems']:<8}) "
                  f"{enhanced_pass:>8.2%} ({results['enhanced']['solved_problems']}/{results['enhanced']['total_problems']:<8}) "
                  f"{pass_improvement:>+8.2%}")
            
            print("\n" + "="*80)
            
            # 总结
            if acc_improvement > 0 or pass_improvement > 0:
                print("✅ Training-Free GRPO 带来了性能提升！")
                if acc_improvement > 0:
                    print(f"   - Accuracy 提升: {acc_improvement:+.2%}")
                if pass_improvement > 0:
                    print(f"   - Pass@32 提升: {pass_improvement:+.2%}")
            elif acc_improvement < 0 or pass_improvement < 0:
                print("⚠️  性能下降，可能需要调整训练参数")
            else:
                print("➡️  性能持平")
            
            print("="*80 + "\n")
            
            # 显示每个题目的正确答案数
            print("每个题目的正确答案数统计:\n")
            print(f"{'题目':<6} {'Baseline正确数':<18} {'Practice正确数':<18} {'变化':<10}")
            print("-" * 60)
            
            baseline_stats = results["baseline"]["per_problem_stats"]
            practice_stats = results["enhanced"]["per_problem_stats"]
            
            # 创建问题到统计的映射
            baseline_map = {s['problem']: s for s in baseline_stats}
            practice_map = {s['problem']: s for s in practice_stats}
            
            all_problems = set(baseline_map.keys()) | set(practice_map.keys())
            
            for i, problem in enumerate(sorted(all_problems), 1):
                baseline_correct = baseline_map.get(problem, {}).get('correct', 0)
                practice_correct = practice_map.get(problem, {}).get('correct', 0)
                change = practice_correct - baseline_correct
                change_str = f"{change:+d}" if change != 0 else "0"
                
                print(f"{i:<6} {baseline_correct}/32{'':<10} {practice_correct}/32{'':<10} {change_str:<10}")
            
            print("="*80 + "\n")
            
        elif results["baseline"] and not results["enhanced"]:
            print("✅ Baseline 评估已完成")
            print(f"   - Accuracy: {results['baseline']['accuracy']:.2%}")
            print(f"   - Pass@32: {results['baseline']['pass_at_32']:.2%}")
            print("\n⏳ 请运行 Training-Free GRPO 和 Enhanced 评估")
            print("   1. uv run python scripts/run_training_free_GRPO.py --config practice/logic_reasoning_zebralogic.yaml")
            print("   2. uv run python scripts/run_eval.py --config eval/logic/logic_practice_zebralogic_test.yaml")
            print()
            
        elif not results["baseline"] and results["enhanced"]:
            print("⚠️  只找到 Enhanced 评估数据，缺少 Baseline")
            print("请先运行 Baseline 评估：")
            print("   uv run python scripts/run_eval.py --config eval/logic/logic_zebralogic_test.yaml")
            print()
            
        else:
            print("❌ 未找到任何评估数据")
            print("\n请按以下步骤运行实验：")
            print("   1. Baseline: uv run python scripts/run_eval.py --config eval/logic/logic_zebralogic_test.yaml")
            print("   2. GRPO: uv run python scripts/run_training_free_GRPO.py --config practice/logic_reasoning_zebralogic.yaml")
            print("   3. Enhanced: uv run python scripts/run_eval.py --config eval/logic/logic_practice_zebralogic_test.yaml")
            print()


if __name__ == "__main__":
    compare_results()

