"""
查看 Training-Free GRPO 训练前后的结果对比
View Training-Free GRPO before/after results comparison

用法 / Usage:
1. 查看论文实验结果对比:
   python scripts/view_training_results.py

2. 查看详细的 pass@k 统计:
   python scripts/view_training_results.py --detailed

3. 导出结果为 JSON:
   python scripts/view_training_results.py --export results.json

4. 查看特定实验:
   python scripts/view_training_results.py --exp_ids math_paper_exp_AIME24_eval math_practice_paper_exp_AIME24_eval
"""

import argparse
import json
from collections import defaultdict
from typing import Dict, List, Tuple

from sqlmodel import Session, create_engine, select
from utu.db import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def get_experiment_stats(session: Session, exp_id: str) -> Dict:
    """获取单个实验的统计数据"""
    samples = session.exec(
        select(EvaluationSample).where(EvaluationSample.exp_id == exp_id)
    ).all()
    
    if not samples:
        return None
    
    total = len(samples)
    correct = sum(1 for s in samples if s.reward == 1.0)
    accuracy = correct / total * 100 if total > 0 else 0
    
    # 按问题分组计算 pass@k
    question_results = defaultdict(list)
    for sample in samples:
        question_results[sample.raw_question].append(sample.reward)
    
    # 计算不同 k 值的 pass@k
    pass_at_k = {}
    for k in [1, 5, 10, 32]:
        passed = 0
        for question, rewards in question_results.items():
            # 取前 k 个结果，如果有任何一个正确则算通过
            if any(r == 1.0 for r in rewards[:k]):
                passed += 1
        pass_at_k[k] = (passed / len(question_results) * 100) if question_results else 0
    
    return {
        "exp_id": exp_id,
        "total_samples": total,
        "correct_samples": correct,
        "accuracy": accuracy,
        "unique_questions": len(question_results),
        "pass_at_k": pass_at_k,
        "samples_per_question": total / len(question_results) if question_results else 0
    }


def print_experiment_stats(stats: Dict, detailed: bool = False):
    """打印实验统计信息"""
    if not stats:
        print("  (无数据)")
        return
    
    print(f"  实验ID: {stats['exp_id']}")
    print(f"  总样本数: {stats['total_samples']}")
    print(f"  唯一问题数: {stats['unique_questions']}")
    print(f"  每题样本数: {stats['samples_per_question']:.1f}")
    print(f"  正确样本数: {stats['correct_samples']}")
    print(f"  准确率: {stats['accuracy']:.2f}%")
    
    if detailed and stats['pass_at_k']:
        print(f"\n  Pass@K 指标:")
        for k, rate in sorted(stats['pass_at_k'].items()):
            print(f"    Pass@{k}: {rate:.2f}%")


def compare_experiments(before_stats: Dict, after_stats: Dict) -> Dict:
    """对比训练前后的实验结果"""
    if not before_stats or not after_stats:
        return None
    
    comparison = {
        "before": before_stats,
        "after": after_stats,
        "improvement": {
            "accuracy": after_stats['accuracy'] - before_stats['accuracy'],
            "correct_samples": after_stats['correct_samples'] - before_stats['correct_samples'],
        },
        "pass_at_k_improvement": {}
    }
    
    # 计算 pass@k 的提升
    for k in before_stats['pass_at_k'].keys():
        if k in after_stats['pass_at_k']:
            comparison['pass_at_k_improvement'][k] = (
                after_stats['pass_at_k'][k] - before_stats['pass_at_k'][k]
            )
    
    return comparison


def print_comparison(comparison: Dict, dataset_name: str):
    """打印对比结果"""
    if not comparison:
        print(f"\n  {dataset_name}: 数据不完整，无法对比")
        return
    
    before = comparison['before']
    after = comparison['after']
    improvement = comparison['improvement']
    
    print(f"\n{'='*70}")
    print(f"{dataset_name} 结果对比")
    print(f"{'='*70}")
    
    print(f"\n【训练前 (Baseline)】")
    print(f"  准确率: {before['accuracy']:.2f}%")
    print(f"  正确数: {before['correct_samples']}/{before['total_samples']}")
    
    print(f"\n【训练后 (After Training-Free GRPO)】")
    print(f"  准确率: {after['accuracy']:.2f}%")
    print(f"  正确数: {after['correct_samples']}/{after['total_samples']}")
    
    print(f"\n【提升 (Improvement)】")
    print(f"  准确率变化: {improvement['accuracy']:+.2f}%")
    print(f"  正确数变化: {improvement['correct_samples']:+d}")
    
    if comparison['pass_at_k_improvement']:
        print(f"\n【Pass@K 对比】")
        print(f"  {'K值':<10} {'训练前':<15} {'训练后':<15} {'提升':<15}")
        print(f"  {'-'*10} {'-'*15} {'-'*15} {'-'*15}")
        
        for k in sorted(comparison['pass_at_k_improvement'].keys()):
            before_val = before['pass_at_k'][k]
            after_val = after['pass_at_k'][k]
            improvement_val = comparison['pass_at_k_improvement'][k]
            
            print(f"  Pass@{k:<5} {before_val:>6.2f}%{'':<7} {after_val:>6.2f}%{'':<7} {improvement_val:>+6.2f}%{'':<7}")


def view_paper_experiment_results(detailed: bool = False):
    """查看论文实验的结果"""
    experiments = {
        "AIME 2024": {
            "before": "math_paper_exp_AIME24_eval",
            "after": "math_practice_paper_exp_AIME24_eval"
        },
        "AIME 2025": {
            "before": "math_paper_exp_AIME25_eval",
            "after": "math_practice_paper_exp_AIME25_eval"
        }
    }
    
    with SQLModelUtils.create_session() as session:
        print("\n" + "="*70)
        print("Training-Free GRPO 论文实验结果")
        print("="*70)
        
        all_comparisons = {}
        
        for dataset_name, exp_ids in experiments.items():
            before_stats = get_experiment_stats(session, exp_ids["before"])
            after_stats = get_experiment_stats(session, exp_ids["after"])
            
            if before_stats and after_stats:
                comparison = compare_experiments(before_stats, after_stats)
                all_comparisons[dataset_name] = comparison
                print_comparison(comparison, dataset_name)
            else:
                print(f"\n{dataset_name}: ")
                if not before_stats:
                    print(f"  ⚠ 未找到训练前数据: {exp_ids['before']}")
                if not after_stats:
                    print(f"  ⚠ 未找到训练后数据: {exp_ids['after']}")
        
        # 总结
        if all_comparisons:
            print(f"\n{'='*70}")
            print("总结 (Summary)")
            print(f"{'='*70}\n")
            
            for dataset_name, comparison in all_comparisons.items():
                improvement = comparison['improvement']['accuracy']
                symbol = "✓" if improvement > 0 else ("✗" if improvement < 0 else "○")
                print(f"  {symbol} {dataset_name}: {improvement:+.2f}%")
        
        print(f"\n{'='*70}\n")
        
        return all_comparisons


def view_specific_experiments(exp_ids: List[str], detailed: bool = False):
    """查看特定实验的结果"""
    with SQLModelUtils.create_session() as session:
        print("\n" + "="*70)
        print("实验统计信息")
        print("="*70)
        
        results = {}
        for exp_id in exp_ids:
            print(f"\n{exp_id}:")
            stats = get_experiment_stats(session, exp_id)
            if stats:
                print_experiment_stats(stats, detailed)
                results[exp_id] = stats
            else:
                print(f"  ⚠ 未找到实验数据")
        
        print(f"\n{'='*70}\n")
        return results


def export_results(data: Dict, filename: str):
    """导出结果为 JSON"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✓ 结果已导出到: {filename}")


def main():
    parser = argparse.ArgumentParser(
        description="查看 Training-Free GRPO 训练前后的结果对比",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--detailed", "-d",
        action="store_true",
        help="显示详细的 Pass@K 统计"
    )
    
    parser.add_argument(
        "--exp_ids", "-e",
        nargs="+",
        help="查看特定实验（可以指定多个）"
    )
    
    parser.add_argument(
        "--export", "-o",
        type=str,
        metavar="FILE",
        help="导出结果为 JSON 文件"
    )
    
    args = parser.parse_args()
    
    if args.exp_ids:
        # 查看特定实验
        results = view_specific_experiments(args.exp_ids, args.detailed)
    else:
        # 默认查看论文实验结果
        results = view_paper_experiment_results(args.detailed)
    
    # 导出结果
    if args.export:
        export_results(results, args.export)


if __name__ == "__main__":
    main()




