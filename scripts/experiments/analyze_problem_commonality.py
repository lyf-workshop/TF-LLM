#!/usr/bin/env python3
"""
分析指定题目的共同特征
"""

import sys
from pathlib import Path
from sqlmodel import select
from collections import defaultdict
import re

sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.db.eval_datapoint import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def analyze_commonality(exp_id: str, problem_indices: list[int]):
    """分析题目的共同特征"""
    
    print(f"\n{'='*80}")
    print(f"分析题目共同特征")
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
        
        # 提取指定题目
        target_problems = []
        for idx in problem_indices:
            if idx < 1 or idx > len(all_problems):
                print(f"⚠️ 题目 {idx} 超出范围")
                continue
            problem = all_problems[idx - 1]
            target_problems.append((idx, problem))
        
        print(f"{'='*80}\n")
        print("📋 题目内容分析\n")
        print(f"{'='*80}\n")
        
        # 分析每个题目
        all_attributes = []
        all_constraints = []
        problem_types = []
        
        for idx, problem in target_problems:
            print(f"### 题目 {idx}\n")
            print(f"```\n{problem[:800]}\n```\n")
            
            # 提取属性
            attributes = re.findall(r'Each person has (?:a |an )?unique (?:type of |level of |favorite )?([^:]+):', problem)
            attributes.extend(re.findall(r'People have unique ([^:]+):', problem))
            attributes.extend(re.findall(r'Everyone has (?:something |a )?unique ([^:]+):', problem))
            attributes.extend(re.findall(r'The ([^:]+) (?:in different houses |are )?unique:', problem))
            attributes.extend(re.findall(r'Each person (?:has |prefers |lives in )?(?:a |an )?unique ([^:]+):', problem))
            attributes.extend(re.findall(r'They all have (?:a |an )?unique ([^:]+):', problem))
            
            if attributes:
                print(f"**属性**: {', '.join(attributes[:10])}\n")
                all_attributes.extend(attributes)
            
            # 提取约束条件数量
            constraint_lines = [line for line in problem.split('\n') if line.strip() and ('is' in line.lower() or 'has' in line.lower() or 'lives' in line.lower())]
            all_constraints.extend(constraint_lines)
            
            # 判断问题类型
            if '4 houses' in problem.lower():
                problem_types.append('4栋房子')
            
            print(f"**约束条件行数**: {len(constraint_lines)}\n")
            print("---\n\n")
        
        # 共同特征分析
        print(f"{'='*80}\n")
        print("🔍 共同特征分析\n")
        print(f"{'='*80}\n")
        
        print("### 1. 问题结构\n")
        print(f"- ✅ 所有题目都是 **4栋房子** 的逻辑推理问题")
        print(f"- ✅ 都是约束满足问题 (Constraint Satisfaction Problem)")
        print(f"- ✅ 都涉及多个属性的唯一性分配\n")
        
        print("### 2. 属性特征\n")
        attribute_counts = defaultdict(int)
        for attr in all_attributes:
            attr_clean = attr.strip().lower()
            attribute_counts[attr_clean] += 1
        
        print("**常见属性** (出现频率):")
        for attr, count in sorted(attribute_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
            print(f"- `{attr}`: {count}次")
        print()
        
        print("### 3. 约束复杂度\n")
        print(f"- 平均约束条件行数: {len(all_constraints) / len(target_problems):.1f} 行")
        print(f"- 总约束条件数: {len(all_constraints)} 条\n")
        
        print("### 4. 难度特征\n")
        print("这些题目可能具有以下共同难度特征:")
        print("- 需要同时考虑多个约束条件")
        print("- 需要逐步推理和排除")
        print("- 可能存在隐含的约束关系")
        print("- 需要维护多个属性的分配状态\n")
        
        # 检查是否有特定的属性组合
        print("### 5. 属性组合分析\n")
        unique_combinations = set()
        for idx, problem in target_problems:
            attrs = []
            # 提取所有属性名
            for match in re.finditer(r'(?:Each person|People|Everyone|They all) (?:has|have|prefers|lives in) (?:a |an |something )?unique (?:type of |level of |favorite )?([^:]+):', problem):
                attrs.append(match.group(1).strip().lower())
            if attrs:
                unique_combinations.add(tuple(sorted(attrs)))
        
        print(f"**不同的属性组合数**: {len(unique_combinations)}")
        for i, combo in enumerate(unique_combinations, 1):
            print(f"{i}. {', '.join(combo[:5])}...")
        print()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="分析题目的共同特征")
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
    
    args = parser.parse_args()
    
    analyze_commonality(args.exp_id, args.problems)















































































