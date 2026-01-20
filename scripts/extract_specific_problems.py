#!/usr/bin/env python3
"""
提取指定题目编号的完整问题和答案
"""

import sys
from pathlib import Path
from sqlmodel import select
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.db.eval_datapoint import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def extract_problems(exp_id: str, problem_indices: list[int], output_file: str):
    """提取指定题目的完整信息"""
    
    print(f"\n{'='*80}")
    print(f"提取题目信息")
    print(f"{'='*80}\n")
    print(f"实验 ID: {exp_id}")
    print(f"题目编号: {problem_indices}")
    print(f"输出文件: {output_file}\n")
    
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
        
        # 获取所有问题（按出现顺序）
        all_problems = list(problem_to_samples.keys())
        
        print(f"总问题数: {len(all_problems)}")
        print(f"总样本数: {len(samples)}\n")
        
        # 生成报告
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"# 指定题目详细信息\n\n")
            f.write(f"**实验 ID**: `{exp_id}`\n")
            f.write(f"**提取的题目编号**: {', '.join(str(i) for i in problem_indices)}\n\n")
            f.write("---\n\n")
            
            for idx in problem_indices:
                if idx < 1 or idx > len(all_problems):
                    f.write(f"## 题目 {idx}\n\n")
                    f.write(f"❌ 题目编号超出范围 (1-{len(all_problems)})\n\n")
                    f.write("---\n\n")
                    continue
                
                # 获取题目
                problem = all_problems[idx - 1]
                problem_samples = problem_to_samples[problem]
                
                # 统计信息
                correct_count = sum(1 for s in problem_samples if s.reward and s.reward > 0.5)
                total_count = len(problem_samples)
                
                f.write(f"## 题目 {idx}\n\n")
                
                # 问题内容
                f.write(f"**完整问题**:\n```\n{problem}\n```\n\n")
                
                # 统计信息
                f.write("**统计信息**:\n")
                f.write(f"- 总答案数: {total_count}\n")
                f.write(f"- 正确答案数: {correct_count}\n")
                f.write(f"- 错误答案数: {total_count - correct_count}\n")
                f.write(f"- 正确率: {correct_count / total_count * 100:.2f}%\n\n")
                
                # 正确答案
                if problem_samples and problem_samples[0].correct_answer:
                    f.write(f"**正确答案**:\n```\n{problem_samples[0].correct_answer}\n```\n\n")
                
                # 正确答案的rollout编号
                if correct_count > 0:
                    correct_rollouts = []
                    for sample_idx, sample in enumerate(problem_samples, 1):
                        if sample.reward and sample.reward > 0.5:
                            correct_rollouts.append(str(sample_idx))
                    f.write(f"**正确答案的 Rollout 编号**: {', '.join(correct_rollouts)}\n\n")
                else:
                    f.write("**正确答案的 Rollout 编号**: 无\n\n")
                
                # 所有rollouts的reward列表
                f.write("**所有 Rollouts 的 Reward**:\n")
                f.write("```\n")
                for sample_idx, sample in enumerate(problem_samples, 1):
                    if sample.reward is not None:
                        reward_str = f"{sample.reward:.1f}"
                        status = "✓" if sample.reward > 0.5 else "✗"
                    else:
                        reward_str = "N/A"
                        status = "✗"
                    f.write(f"Rollout {sample_idx:2d}: {reward_str:>4s} {status}\n")
                f.write("```\n\n")
                
                # 示例：显示第一个正确的回答
                if correct_count > 0:
                    for sample_idx, sample in enumerate(problem_samples, 1):
                        if sample.reward and sample.reward > 0.5:
                            f.write(f"**示例正确回答 (Rollout {sample_idx})**:\n")
                            if sample.response:
                                f.write(f"```\n{sample.response}\n```\n\n")
                            break
                
                f.write("---\n\n")
        
        print(f"报告已生成: {output_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="提取指定题目的完整信息")
    parser.add_argument(
        "--exp_id",
        type=str,
        default="logic_zebralogic_test_eval",
        help="实验 ID"
    )
    parser.add_argument(
        "--problems",
        type=int,
        nargs="+",
        default=[4, 5, 11, 22, 23],
        help="题目编号（空格分隔）"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="指定题目详细信息.md",
        help="输出文件"
    )
    
    args = parser.parse_args()
    
    extract_problems(args.exp_id, args.problems, args.output)















































































