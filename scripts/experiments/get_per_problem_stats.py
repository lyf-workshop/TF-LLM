#!/usr/bin/env python3
"""
统计每个题目的32个答案中的正确答案数
"""

import sys
from pathlib import Path
from sqlmodel import select
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.db.eval_datapoint import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def get_per_problem_stats(exp_id: str):
    """获取每个题目的统计信息"""
    
    print(f"\n{'='*80}")
    print(f"统计实验: {exp_id}")
    print(f"{'='*80}\n")
    
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
        
        # 统计每个问题
        results = []
        for problem, problem_samples in sorted(problem_to_samples.items()):
            correct_count = sum(1 for s in problem_samples if s.reward and s.reward > 0.5)
            total_count = len(problem_samples)
            
            results.append({
                'problem': problem[:100] + '...' if len(problem) > 100 else problem,
                'total': total_count,
                'correct': correct_count,
                'wrong': total_count - correct_count,
            })
        
        # 显示结果
        print(f"{'题目':<6} {'总答案数':<10} {'正确答案数':<12} {'错误答案数':<12}")
        print("-" * 50)
        
        for i, r in enumerate(results, 1):
            print(f"{i:<6} {r['total']:<10} {r['correct']:<12} {r['wrong']:<12}")
        
        total_samples = sum(r['total'] for r in results)
        total_correct = sum(r['correct'] for r in results)
        print("-" * 50)
        print(f"{'总计':<6} {total_samples:<10} {total_correct:<12} {total_samples - total_correct:<12}")
        print()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true", help="分析 baseline")
    parser.add_argument("--practice", action="store_true", help="分析 practice")
    parser.add_argument("--exp_id", type=str, help="实验 ID")
    
    args = parser.parse_args()
    
    if args.exp_id:
        get_per_problem_stats(args.exp_id)
    elif args.baseline:
        get_per_problem_stats("logic_zebralogic_test_eval")
    elif args.practice:
        get_per_problem_stats("logic_practice_zebralogic_test_eval")
    else:
        print("分析 Baseline:")
        get_per_problem_stats("logic_zebralogic_test_eval")
        print("\n分析 Practice:")
        get_per_problem_stats("logic_practice_zebralogic_test_eval")

















































































