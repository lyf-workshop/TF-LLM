#!/usr/bin/env python3
"""查看评估的详细信息，包括问题、模型答案、标准答案"""

import argparse
import json
from typing import Optional
from sqlmodel import select

from utu.db.eval_datapoint import EvaluationSample, DatasetSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def view_evaluation_details(exp_id: str, limit: Optional[int] = None, show_correct_only: bool = False, show_wrong_only: bool = False):
    """查看评估的详细信息"""
    
    print("\n" + "="*80)
    print(f"实验详情: {exp_id}")
    print("="*80 + "\n")
    
    with SQLModelUtils.create_session() as session:
        # 获取评估样本
        statement = select(EvaluationSample).where(EvaluationSample.exp_id == exp_id)
        samples = list(session.exec(statement))
        
        if not samples:
            print(f"❌ 未找到实验 '{exp_id}' 的数据")
            return
        
        # 按问题分组
        problem_to_samples = {}
        for sample in samples:
            key = sample.raw_question or sample.question
            if key not in problem_to_samples:
                problem_to_samples[key] = []
            problem_to_samples[key].append(sample)
        
        print(f"📊 总体统计:")
        print(f"  总样本数: {len(samples)}")
        print(f"  问题数: {len(problem_to_samples)}")
        print(f"  每题采样数: {len(samples) // len(problem_to_samples) if problem_to_samples else 0}")
        
        # 计算准确率
        correct_samples = [s for s in samples if s.reward and s.reward > 0.5]
        accuracy = len(correct_samples) / len(samples) if samples else 0
        print(f"  准确率: {accuracy:.2%} ({len(correct_samples)}/{len(samples)})")
        
        print("\n" + "-"*80 + "\n")
        
        # 显示每个问题的详情
        problem_count = 0
        for problem_idx, (question, problem_samples) in enumerate(problem_to_samples.items(), 1):
            if limit and problem_count >= limit:
                break
            
            # 统计这个问题的正确率
            correct_count = sum(1 for s in problem_samples if s.reward and s.reward > 0.5)
            problem_accuracy = correct_count / len(problem_samples) if problem_samples else 0
            
            # 过滤条件
            if show_correct_only and correct_count == 0:
                continue
            if show_wrong_only and correct_count > 0:
                continue
            
            problem_count += 1
            
            print(f"{'='*80}")
            print(f"问题 #{problem_idx} - 正确率: {problem_accuracy:.2%} ({correct_count}/{len(problem_samples)})")
            print(f"{'='*80}\n")
            
            # 显示问题内容（截断）
            question_preview = question[:200] + "..." if len(question) > 200 else question
            print(f"📝 问题内容:")
            print(f"{question_preview}\n")
            
            # 获取标准答案（从数据集）
            first_sample = problem_samples[0]
            if first_sample.data_id:
                dataset_sample = session.get(DatasetSample, first_sample.data_id)
                if dataset_sample and dataset_sample.answer:
                    print(f"✅ 标准答案:")
                    try:
                        # 尝试解析 JSON
                        answer_data = json.loads(dataset_sample.answer)
                        print(json.dumps(answer_data, indent=2, ensure_ascii=False))
                    except json.JSONDecodeError:
                        print(f"{dataset_sample.answer}")
                    print()
            
            # 显示模型输出（只显示前几个）
            print(f"🤖 模型输出样本 (显示前5个):\n")
            for i, sample in enumerate(problem_samples[:5], 1):
                reward_symbol = "✅" if sample.reward and sample.reward > 0.5 else "❌"
                reward_value = sample.reward if sample.reward is not None else 0.0
                
                print(f"  样本 #{i} {reward_symbol} (reward: {reward_value:.2f})")
                
                # 显示输出（截断）
                if sample.output:
                    output_preview = sample.output[:300] + "..." if len(sample.output) > 300 else sample.output
                    print(f"  输出: {output_preview}")
                else:
                    print(f"  输出: (空)")
                
                # 显示提取的答案
                if hasattr(sample, 'extracted_answer') and sample.extracted_answer:
                    print(f"  提取的答案: {sample.extracted_answer}")
                
                print()
            
            if len(problem_samples) > 5:
                print(f"  ... 还有 {len(problem_samples) - 5} 个样本\n")
            
            print("-"*80 + "\n")
        
        if limit and problem_count >= limit:
            print(f"\n已显示 {limit} 个问题。使用 --limit 参数查看更多。")


def main():
    parser = argparse.ArgumentParser(description="查看评估的详细信息")
    parser.add_argument(
        "exp_id",
        nargs="?",
        default="logic_zebralogic_test_eval",
        help="实验ID (默认: logic_zebralogic_test_eval)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="限制显示的问题数量"
    )
    parser.add_argument(
        "--correct",
        action="store_true",
        help="只显示至少有一个正确答案的问题"
    )
    parser.add_argument(
        "--wrong",
        action="store_true",
        help="只显示全部错误的问题"
    )
    
    args = parser.parse_args()
    
    view_evaluation_details(
        args.exp_id,
        limit=args.limit,
        show_correct_only=args.correct,
        show_wrong_only=args.wrong
    )


if __name__ == "__main__":
    main()

