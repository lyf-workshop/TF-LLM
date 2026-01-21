#!/usr/bin/env python3
"""
查看指定题目的完整详细内容
"""

import sys
from pathlib import Path
from sqlmodel import select
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.db.eval_datapoint import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def view_problem_details(exp_id: str, problem_indices: list[int], output_file: str = None):
    """查看题目的完整详细内容"""
    
    print(f"\n{'='*80}")
    print(f"查看题目详细内容")
    print(f"{'='*80}\n")
    print(f"实验 ID: {exp_id}")
    print(f"题目编号: {problem_indices}\n")
    
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
        
        print(f"总问题数: {len(all_problems)}\n")
        
        output_lines = []
        output_lines.append(f"# 题目详细内容\n\n")
        output_lines.append(f"**实验 ID**: `{exp_id}`\n")
        output_lines.append(f"**题目编号**: {', '.join(str(i) for i in problem_indices)}\n\n")
        output_lines.append("---\n\n")
        
        for idx in problem_indices:
            if idx < 1 or idx > len(all_problems):
                output_lines.append(f"## 题目 {idx}\n\n")
                output_lines.append(f"❌ 题目编号超出范围 (1-{len(all_problems)})\n\n")
                output_lines.append("---\n\n")
                continue
            
            # 获取题目
            problem = all_problems[idx - 1]
            problem_samples = problem_to_samples[problem]
            sample = problem_samples[0]  # 使用第一个样本
            
            print(f"处理题目 {idx}...")
            
            output_lines.append(f"## 题目 {idx}\n\n")
            
            # 完整问题内容
            output_lines.append(f"### 完整问题\n\n")
            output_lines.append(f"```\n{problem}\n```\n\n")
            
            # 正确答案
            if sample.correct_answer:
                output_lines.append(f"### 正确答案\n\n")
                output_lines.append(f"```\n{sample.correct_answer}\n```\n\n")
            
            # 统计信息
            correct_count = sum(1 for s in problem_samples if s.reward and s.reward > 0.5)
            total_count = len(problem_samples)
            
            output_lines.append(f"### 统计信息\n\n")
            output_lines.append(f"- **总答案数**: {total_count}\n")
            output_lines.append(f"- **正确答案数**: {correct_count}\n")
            output_lines.append(f"- **错误答案数**: {total_count - correct_count}\n")
            output_lines.append(f"- **正确率**: {correct_count / total_count * 100:.2f}%\n\n")
            
            # 属性提取
            output_lines.append(f"### 属性分析\n\n")
            attributes = []
            lines = problem.split('\n')
            for line in lines:
                line = line.strip()
                if line and ('unique' in line.lower() or 'different' in line.lower()):
                    if line.startswith('-'):
                        line = line[1:].strip()
                    attributes.append(line)
            
            if attributes:
                output_lines.append("**涉及的属性**:\n\n")
                for i, attr in enumerate(attributes, 1):
                    output_lines.append(f"{i}. {attr}\n")
                output_lines.append("\n")
            
            # 约束条件提取
            output_lines.append(f"### 约束条件\n\n")
            constraints = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('There are') and not line.startswith('Each house') and not line.startswith('Each person') and 'unique' not in line.lower() and 'different' not in line.lower():
                    if line and (line[0].isupper() or line.startswith('-')):
                        if line.startswith('-'):
                            line = line[1:].strip()
                        constraints.append(line)
            
            if constraints:
                for i, constraint in enumerate(constraints[:20], 1):  # 限制显示前20条
                    output_lines.append(f"{i}. {constraint}\n")
                if len(constraints) > 20:
                    output_lines.append(f"\n... (还有 {len(constraints) - 20} 条约束条件)\n")
                output_lines.append("\n")
            else:
                output_lines.append("(约束条件嵌入在问题描述中)\n\n")
            
            # 示例答案（第一个正确的）
            if correct_count > 0:
                for sample_idx, s in enumerate(problem_samples, 1):
                    if s.reward and s.reward > 0.5:
                        output_lines.append(f"### 示例正确答案 (Rollout {sample_idx})\n\n")
                        if s.response:
                            output_lines.append(f"```\n{s.response}\n```\n\n")
                        break
            
            # 示例错误答案（第一个错误的）
            if correct_count < total_count:
                for sample_idx, s in enumerate(problem_samples, 1):
                    if not s.reward or s.reward <= 0.5:
                        output_lines.append(f"### 示例错误答案 (Rollout {sample_idx})\n\n")
                        if s.response:
                            # 只显示前1000字符
                            response_preview = s.response[:1000]
                            if len(s.response) > 1000:
                                response_preview += "\n... (截断)"
                            output_lines.append(f"```\n{response_preview}\n```\n\n")
                        break
            
            output_lines.append("---\n\n")
        
        # 输出
        output_text = ''.join(output_lines)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output_text)
            print(f"✅ 详细内容已保存到: {output_file}")
        else:
            print(output_text)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="查看题目的完整详细内容")
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
        default="题目详细内容_4_5_11_22_23.md",
        help="输出文件"
    )
    
    args = parser.parse_args()
    
    view_problem_details(args.exp_id, args.problems, args.output)















































































