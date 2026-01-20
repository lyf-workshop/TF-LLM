#!/usr/bin/env python3
"""
对比训练前后指定题目的详细变化
"""

import sys
from pathlib import Path
from sqlmodel import select
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.db.eval_datapoint import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def compare_problems(baseline_exp: str, practice_exp: str, problem_indices: list[int], output_file: str):
    """对比训练前后指定题目的变化"""
    
    print(f"\n{'='*80}")
    print(f"对比训练前后题目变化")
    print(f"{'='*80}\n")
    print(f"Baseline: {baseline_exp}")
    print(f"Practice: {practice_exp}")
    print(f"题目编号: {problem_indices}\n")
    
    with SQLModelUtils.create_session() as session:
        # 获取baseline数据
        baseline_samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == baseline_exp
            ).order_by(EvaluationSample.dataset_index)
        ))
        
        # 获取practice数据
        practice_samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == practice_exp
            ).order_by(EvaluationSample.dataset_index)
        ))
        
        if not baseline_samples or not practice_samples:
            print(f"未找到数据")
            return
        
        # 按问题分组
        def group_by_problem(samples):
            problem_to_samples = defaultdict(list)
            for sample in samples:
                key = sample.raw_question or sample.question
                problem_to_samples[key].append(sample)
            return list(problem_to_samples.values())
        
        baseline_problems = group_by_problem(baseline_samples)
        practice_problems = group_by_problem(practice_samples)
        
        print(f"Baseline 问题数: {len(baseline_problems)}, 样本数: {len(baseline_samples)}")
        print(f"Practice 问题数: {len(practice_problems)}, 样本数: {len(practice_samples)}\n")
        
        # 生成报告
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"# 训练前后指定题目详细对比\n\n")
            f.write(f"**Baseline**: `{baseline_exp}`\n")
            f.write(f"**Practice**: `{practice_exp}`\n")
            f.write(f"**对比题目**: {', '.join(str(i) for i in problem_indices)}\n\n")
            f.write("---\n\n")
            
            # 汇总统计
            f.write("## 汇总统计\n\n")
            f.write("| 题目编号 | Baseline正确率 | Practice正确率 | 变化 | Baseline正确数 | Practice正确数 |\n")
            f.write("|---------|---------------|---------------|------|---------------|---------------|\n")
            
            for idx in problem_indices:
                if idx < 1 or idx > len(baseline_problems):
                    continue
                
                baseline_prob = baseline_problems[idx - 1]
                practice_prob = practice_problems[idx - 1]
                
                baseline_correct = sum(1 for s in baseline_prob if s.reward and s.reward > 0.5)
                practice_correct = sum(1 for s in practice_prob if s.reward and s.reward > 0.5)
                
                baseline_acc = baseline_correct / len(baseline_prob) * 100
                practice_acc = practice_correct / len(practice_prob) * 100
                change = practice_acc - baseline_acc
                
                change_str = f"{change:+.2f}%"
                if change > 0:
                    change_icon = "📈 " + change_str
                elif change < 0:
                    change_icon = "📉 " + change_str
                else:
                    change_icon = "➡️ " + change_str
                
                f.write(f"| {idx} | {baseline_acc:.2f}% | {practice_acc:.2f}% | {change_icon} | {baseline_correct}/32 | {practice_correct}/32 |\n")
            
            f.write("\n---\n\n")
            
            # 详细对比
            for idx in problem_indices:
                if idx < 1 or idx > len(baseline_problems):
                    f.write(f"## 题目 {idx}\n\n")
                    f.write(f"❌ 题目编号超出范围\n\n")
                    f.write("---\n\n")
                    continue
                
                baseline_prob = baseline_problems[idx - 1]
                practice_prob = practice_problems[idx - 1]
                
                f.write(f"## 题目 {idx}\n\n")
                
                # 问题内容
                question = baseline_prob[0].raw_question or baseline_prob[0].question
                f.write(f"### 问题内容\n\n")
                f.write(f"```\n{question}\n```\n\n")
                
                # 正确答案
                if baseline_prob[0].correct_answer:
                    f.write(f"### 正确答案\n\n")
                    f.write(f"```\n{baseline_prob[0].correct_answer}\n```\n\n")
                
                # 统计对比
                baseline_correct = sum(1 for s in baseline_prob if s.reward and s.reward > 0.5)
                practice_correct = sum(1 for s in practice_prob if s.reward and s.reward > 0.5)
                
                baseline_acc = baseline_correct / len(baseline_prob) * 100
                practice_acc = practice_correct / len(practice_prob) * 100
                change = practice_acc - baseline_acc
                
                f.write(f"### 统计对比\n\n")
                f.write(f"| 指标 | Baseline | Practice | 变化 |\n")
                f.write(f"|------|----------|----------|------|\n")
                f.write(f"| 正确数/总数 | {baseline_correct}/32 | {practice_correct}/32 | {practice_correct - baseline_correct:+d} |\n")
                f.write(f"| 正确率 | {baseline_acc:.2f}% | {practice_acc:.2f}% | {change:+.2f}% |\n\n")
                
                # 分析rollout变化
                improved_rollouts = []  # 从错到对
                regressed_rollouts = []  # 从对到错
                
                for i in range(len(baseline_prob)):
                    b_correct = baseline_prob[i].reward and baseline_prob[i].reward > 0.5
                    p_correct = practice_prob[i].reward and practice_prob[i].reward > 0.5
                    
                    if not b_correct and p_correct:
                        improved_rollouts.append(i + 1)
                    elif b_correct and not p_correct:
                        regressed_rollouts.append(i + 1)
                
                f.write(f"### Rollout 变化分析\n\n")
                
                if improved_rollouts:
                    f.write(f"**✅ 改进的 Rollouts** ({len(improved_rollouts)} 个): {', '.join(str(r) for r in improved_rollouts)}\n\n")
                else:
                    f.write(f"**✅ 改进的 Rollouts**: 无\n\n")
                
                if regressed_rollouts:
                    f.write(f"**❌ 退步的 Rollouts** ({len(regressed_rollouts)} 个): {', '.join(str(r) for r in regressed_rollouts)}\n\n")
                else:
                    f.write(f"**❌ 退步的 Rollouts**: 无\n\n")
                
                # 详细的rollout对比表
                f.write(f"### 所有 Rollouts 对比\n\n")
                f.write("| Rollout | Baseline | Practice | 变化 |\n")
                f.write("|---------|----------|----------|------|\n")
                
                for i in range(len(baseline_prob)):
                    b_reward = baseline_prob[i].reward if baseline_prob[i].reward is not None else 0.0
                    p_reward = practice_prob[i].reward if practice_prob[i].reward is not None else 0.0
                    
                    b_status = "✓" if b_reward > 0.5 else "✗"
                    p_status = "✓" if p_reward > 0.5 else "✗"
                    
                    if b_reward < 0.5 and p_reward > 0.5:
                        change_icon = "✅ 改进"
                    elif b_reward > 0.5 and p_reward < 0.5:
                        change_icon = "❌ 退步"
                    else:
                        change_icon = "➡️ 不变"
                    
                    f.write(f"| {i+1:2d} | {b_reward:.1f} {b_status} | {p_reward:.1f} {p_status} | {change_icon} |\n")
                
                f.write("\n")
                
                # 如果有改进的rollout，显示一个示例
                if improved_rollouts:
                    first_improved = improved_rollouts[0] - 1
                    f.write(f"### 示例：改进的回答 (Rollout {improved_rollouts[0]})\n\n")
                    
                    f.write("#### Baseline (错误)\n\n")
                    if baseline_prob[first_improved].response:
                        response_text = baseline_prob[first_improved].response[:1000]
                        if len(baseline_prob[first_improved].response) > 1000:
                            response_text += "\n... (截断)"
                        f.write(f"```\n{response_text}\n```\n\n")
                    
                    f.write("#### Practice (正确)\n\n")
                    if practice_prob[first_improved].response:
                        response_text = practice_prob[first_improved].response[:1000]
                        if len(practice_prob[first_improved].response) > 1000:
                            response_text += "\n... (截断)"
                        f.write(f"```\n{response_text}\n```\n\n")
                
                f.write("---\n\n")
        
        print(f"✅ 对比报告已生成: {output_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="对比训练前后指定题目的变化")
    parser.add_argument(
        "--baseline",
        type=str,
        default="logic_zebralogic_test_eval",
        help="Baseline 实验 ID"
    )
    parser.add_argument(
        "--practice",
        type=str,
        default="logic_practice_zebralogic_test_eval",
        help="Practice 实验 ID"
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
        default="训练前后题目对比.md",
        help="输出文件"
    )
    
    args = parser.parse_args()
    
    compare_problems(args.baseline, args.practice, args.problems, args.output)















































































