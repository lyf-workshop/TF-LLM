#!/usr/bin/env python3
"""快速查看评估结果"""

from sqlmodel import select, func
from utu.db import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils
from collections import defaultdict


def calculate_pass_at_k(samples, k):
    """计算 Pass@K"""
    question_results = defaultdict(list)
    for sample in samples:
        question_results[sample.raw_question].append(sample.reward)
    
    passed = 0
    for question, rewards in question_results.items():
        if any(r == 1.0 for r in rewards[:k]):
            passed += 1
    
    return (passed / len(question_results) * 100) if question_results else 0


def view_results(exp_ids):
    """查看结果"""
    print("\n" + "=" * 80)
    print("评估结果统计")
    print("=" * 80 + "\n")
    
    with SQLModelUtils.create_session() as session:
        for exp_id in exp_ids:
            samples = list(session.exec(
                select(EvaluationSample).where(EvaluationSample.exp_id == exp_id)
            ))
            
            if not samples:
                print(f"❌ 实验 '{exp_id}' 未找到数据\n")
                continue
            
            total = len(samples)
            correct = sum(1 for s in samples if s.reward == 1.0)
            accuracy = (correct / total * 100) if total > 0 else 0
            
            # 计算 Pass@K
            question_count = len(set(s.raw_question for s in samples))
            k_per_question = total // question_count if question_count > 0 else 1
            
            pass_at_1 = calculate_pass_at_k(samples, 1)
            pass_at_5 = calculate_pass_at_k(samples, min(5, k_per_question))
            
            print(f"📊 {exp_id}")
            print(f"  总样本数: {total}")
            print(f"  问题数: {question_count}")
            print(f"  每题采样: {k_per_question}")
            print(f"  正确数: {correct}")
            print(f"  准确率: {accuracy:.2f}%")
            print(f"  Pass@1: {pass_at_1:.2f}%")
            if k_per_question >= 5:
                print(f"  Pass@5: {pass_at_5:.2f}%")
            print()
    
    print("=" * 80)


if __name__ == "__main__":
    import sys
    
    # 默认查看这些实验
    default_exp_ids = [
        "easy_base_hierarchical",  # 基线
        "easy_practice_hierarchical_num4",  # 训练后
        "medium_reasoning_hierarchical_num1_4_epoch_2",  # Medium 训练
    ]
    
    exp_ids = sys.argv[1:] if len(sys.argv) > 1 else default_exp_ids
    view_results(exp_ids)


























