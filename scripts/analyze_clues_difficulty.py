#!/usr/bin/env python3
"""
通过约束条件数量（格子数量）分析题目难度
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import select
from utu.db.eval_datapoint import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def extract_clues_count(question_text: str) -> int:
    """从问题文本中提取约束条件（clues）的数量"""
    
    # 查找 "## Clues:" 或 "Clues:" 部分
    clues_pattern = r'(?:##\s*)?Clues?\s*:\s*\n'
    clues_match = re.search(clues_pattern, question_text, re.IGNORECASE)
    
    if not clues_match:
        # 如果没有明确的Clues部分，尝试查找编号的约束条件
        # 格式如 "1. ..." 或 "1) ..."
        numbered_clues = re.findall(r'^\s*\d+[\.\)]\s+', question_text, re.MULTILINE)
        return len(numbered_clues)
    
    # 提取Clues部分之后的内容
    clues_start = clues_match.end()
    clues_text = question_text[clues_start:]
    
    # 查找所有编号的约束条件
    # 格式: "1. ..." 或 "1) ..." 或 "1 ..."
    numbered_pattern = r'^\s*(\d+)[\.\)]\s+'
    clues = re.findall(numbered_pattern, clues_text, re.MULTILINE)
    
    if clues:
        # 获取最大的编号
        max_num = max(int(num) for num in clues)
        return max_num
    
    # 如果没有找到编号，尝试计算行数（排除空行）
    lines = [line.strip() for line in clues_text.split('\n') if line.strip()]
    return len(lines)


def analyze_clues_difficulty(exp_id: str, output_file: str):
    """分析约束条件数量与难度的关系"""
    
    print(f"\n{'='*80}")
    print(f"分析约束条件数量（格子数量）与难度的关系")
    print(f"{'='*80}\n")
    print(f"实验 ID: {exp_id}\n")
    
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
        
        # 分析每个问题
        problem_data = []
        for idx, problem in enumerate(all_problems, 1):
            problem_samples = problem_to_samples[problem]
            sample = problem_samples[0]
            
            # 提取约束条件数量
            clues_count = extract_clues_count(problem)
            
            # 计算正确率
            correct_count = sum(1 for s in problem_samples if s.reward and s.reward > 0.5)
            accuracy = correct_count / len(problem_samples) * 100
            
            problem_data.append({
                'id': idx,
                'clues_count': clues_count,
                'correct_count': correct_count,
                'accuracy': accuracy,
                'question': problem[:200]  # 保存前200字符用于检查
            })
            
            print(f"题目 {idx}: {clues_count} 个约束条件, 正确率 {accuracy:.2f}%")
        
        print(f"\n{'='*80}\n")
        
        # 按约束条件数量分组统计
        clues_to_problems = defaultdict(list)
        for p in problem_data:
            clues_to_problems[p['clues_count']].append(p)
        
        # 生成报告
        output_lines = []
        output_lines.append("# 约束条件数量（格子数量）与难度关系分析\n\n")
        output_lines.append("**实验 ID**: `{}`\n\n".format(exp_id))
        output_lines.append("---\n\n")
        
        # 总体统计
        output_lines.append("## 📊 总体统计\n\n")
        avg_clues = sum(p['clues_count'] for p in problem_data) / len(problem_data)
        min_clues = min(p['clues_count'] for p in problem_data)
        max_clues = max(p['clues_count'] for p in problem_data)
        
        output_lines.append(f"- **总题目数**: {len(problem_data)}\n")
        output_lines.append(f"- **平均约束条件数**: {avg_clues:.1f}\n")
        output_lines.append(f"- **最少约束条件**: {min_clues}\n")
        output_lines.append(f"- **最多约束条件**: {max_clues}\n\n")
        output_lines.append("---\n\n")
        
        # 按约束条件数量分组
        output_lines.append("## 📈 按约束条件数量分组统计\n\n")
        output_lines.append("| 约束条件数 | 题目数量 | 平均正确率 | 题目编号 |\n")
        output_lines.append("|-----------|---------|-----------|---------|\n")
        
        for clues_count in sorted(clues_to_problems.keys()):
            problems_in_group = clues_to_problems[clues_count]
            avg_accuracy = sum(p['accuracy'] for p in problems_in_group) / len(problems_in_group)
            problem_ids = ', '.join(str(p['id']) for p in sorted(problems_in_group, key=lambda x: x['id']))
            output_lines.append(f"| {clues_count} | {len(problems_in_group)} | {avg_accuracy:.2f}% | {problem_ids} |\n")
        
        output_lines.append("\n---\n\n")
        
        # 详细列表
        output_lines.append("## 📋 所有题目详细信息\n\n")
        output_lines.append("| 题目编号 | 约束条件数 | 正确数/总数 | 正确率 |\n")
        output_lines.append("|---------|-----------|------------|--------|\n")
        
        for p in sorted(problem_data, key=lambda x: x['clues_count']):
            output_lines.append(f"| {p['id']} | {p['clues_count']} | {p['correct_count']}/32 | {p['accuracy']:.2f}% |\n")
        
        output_lines.append("\n---\n\n")
        
        # 相关性分析
        output_lines.append("## 🔍 相关性分析\n\n")
        
        # 计算相关系数（简单版本）
        clues_counts = [p['clues_count'] for p in problem_data]
        accuracies = [p['accuracy'] for p in problem_data]
        
        correlation = calculate_correlation(clues_counts, accuracies)
        output_lines.append(f"**约束条件数量与正确率的相关系数**: {correlation:.3f}\n\n")
        
        if correlation < -0.3:
            output_lines.append("📉 **负相关较强**: 约束条件越多，正确率越低（题目越难）\n\n")
        elif correlation > 0.3:
            output_lines.append("📈 **正相关较强**: 约束条件越多，正确率越高（题目越容易）\n\n")
        else:
            output_lines.append("📊 **相关性较弱**: 约束条件数量与正确率关系不明显\n\n")
        
        # 按约束条件数量区间的统计
        output_lines.append("### 按约束条件数量区间统计\n\n")
        output_lines.append("| 约束条件数区间 | 题目数量 | 平均正确率 | 题目编号 |\n")
        output_lines.append("|--------------|---------|-----------|---------|\n")
        
        intervals = [
            (0, 10, "0-10"),
            (10, 12, "10-12"),
            (12, 15, "12-15"),
            (15, 20, "15-20"),
            (20, 100, "20+")
        ]
        
        for start, end, label in intervals:
            problems_in_interval = [p for p in problem_data if start <= p['clues_count'] < end]
            if problems_in_interval:
                avg_acc = sum(p['accuracy'] for p in problems_in_interval) / len(problems_in_interval)
                problem_ids = ', '.join(str(p['id']) for p in sorted(problems_in_interval, key=lambda x: x['id']))
                output_lines.append(f"| {label} | {len(problems_in_interval)} | {avg_acc:.2f}% | {problem_ids} |\n")
        
        output_lines.append("\n---\n\n")
        
        # 关键发现
        output_lines.append("## 💡 关键发现\n\n")
        
        # 找出约束条件最少和最多的题目
        min_clues_problems = [p for p in problem_data if p['clues_count'] == min_clues]
        max_clues_problems = [p for p in problem_data if p['clues_count'] == max_clues]
        
        output_lines.append(f"### 约束条件最少的题目 ({min_clues}个)\n\n")
        for p in min_clues_problems:
            output_lines.append(f"- 题目 {p['id']}: 正确率 {p['accuracy']:.2f}%\n")
        
        output_lines.append(f"\n### 约束条件最多的题目 ({max_clues}个)\n\n")
        for p in max_clues_problems:
            output_lines.append(f"- 题目 {p['id']}: 正确率 {p['accuracy']:.2f}%\n")
        
        output_lines.append("\n")
        
        # 关注的5道题目
        target_problems = [4, 5, 11, 22, 23]
        output_lines.append("### 关注的5道题目（4, 5, 11, 22, 23）\n\n")
        output_lines.append("| 题目编号 | 约束条件数 | 正确率 |\n")
        output_lines.append("|---------|-----------|--------|\n")
        
        for target_id in target_problems:
            if target_id <= len(problem_data):
                p = problem_data[target_id - 1]
                output_lines.append(f"| {p['id']} | {p['clues_count']} | {p['accuracy']:.2f}% |\n")
        
        # 保存报告
        output_text = ''.join(output_lines)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output_text)
        
        print(f"✅ 分析报告已生成: {output_file}")


def calculate_correlation(x, y):
    """计算皮尔逊相关系数"""
    n = len(x)
    if n == 0:
        return 0
    
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    
    numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    denominator_x = sum((x[i] - mean_x) ** 2 for i in range(n))
    denominator_y = sum((y[i] - mean_y) ** 2 for i in range(n))
    
    if denominator_x == 0 or denominator_y == 0:
        return 0
    
    return numerator / ((denominator_x * denominator_y) ** 0.5)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="分析约束条件数量与难度的关系")
    parser.add_argument(
        "--exp_id",
        type=str,
        default="logic_zebralogic_test_eval",
        help="实验 ID"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="约束条件数量与难度分析.md",
        help="输出文件"
    )
    
    args = parser.parse_args()
    
    analyze_clues_difficulty(args.exp_id, args.output)















































































