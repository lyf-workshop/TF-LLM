#!/usr/bin/env python3
"""
分析完整对比报告，统计 baseline 和 practice 的正确数量
"""

import re
from pathlib import Path


def analyze_report(report_file: str):
    """分析报告文件，统计正确和错误的数量"""
    
    print("\n" + "=" * 80)
    print("分析完整对比报告")
    print("=" * 80)
    print(f"\n报告文件: {report_file}\n")
    
    with open(report_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取 Baseline rollouts
    baseline_section = re.search(
        r'\*\*训练前 \(Baseline\) - 所有 Rollouts\*\*:(.*?)\*\*训练后 \(Practice\)',
        content,
        re.DOTALL
    )
    
    if not baseline_section:
        print("[错误] 未找到 Baseline 部分")
        return
    
    baseline_content = baseline_section.group(1)
    
    # 统计 Baseline rollouts
    baseline_rollouts = re.findall(r'#### Baseline Rollout \d+\n- Reward: ([\d.]+|N/A)', baseline_content)
    baseline_total = len(baseline_rollouts)
    baseline_correct = sum(1 for r in baseline_rollouts if r == '1.0')
    baseline_wrong = sum(1 for r in baseline_rollouts if r == '0.0')
    
    print("=" * 80)
    print("Baseline (训练前) 统计")
    print("=" * 80)
    print(f"\n总 Rollouts 数: {baseline_total}")
    print(f"正确 (Reward = 1.0): {baseline_correct}")
    print(f"错误 (Reward = 0.0): {baseline_wrong}")
    print(f"正确率: {baseline_correct / baseline_total * 100:.2f}%")
    
    # 提取 Practice rollouts
    practice_section = re.search(
        r'\*\*训练后 \(Practice\) - 所有 Rollouts\*\*:(.*?)(?:\*\*正确答案\*\*|$)',
        content,
        re.DOTALL
    )
    
    if not practice_section:
        print("\n[错误] 未找到 Practice 部分")
        return
    
    practice_content = practice_section.group(1)
    
    # 统计 Practice rollouts
    practice_rollouts = re.findall(r'#### Practice Rollout \d+\n- Reward: ([\d.]+|N/A)', practice_content)
    practice_total = len(practice_rollouts)
    practice_correct = sum(1 for r in practice_rollouts if r == '1.0')
    practice_wrong = sum(1 for r in practice_rollouts if r == '0.0')
    
    print("\n" + "=" * 80)
    print("Practice (训练后) 统计")
    print("=" * 80)
    print(f"\n总 Rollouts 数: {practice_total}")
    print(f"正确 (Reward = 1.0): {practice_correct}")
    print(f"错误 (Reward = 0.0): {practice_wrong}")
    print(f"正确率: {practice_correct / practice_total * 100:.2f}%")
    
    # 找出正确的 rollout 编号
    if practice_correct > 0:
        print("\n正确的 Rollout 编号:")
        correct_rollouts = []
        for match in re.finditer(r'#### Practice Rollout (\d+)\n- Reward: 1\.0', practice_content):
            correct_rollouts.append(match.group(1))
        print(f"   {', '.join(correct_rollouts)}")
    
    # 对比分析
    print("\n" + "=" * 80)
    print("对比分析")
    print("=" * 80)
    
    improvement = practice_correct - baseline_correct
    accuracy_improvement = (practice_correct / practice_total) - (baseline_correct / baseline_total)
    
    print(f"\n正确数量变化: {baseline_correct} → {practice_correct} ({improvement:+d})")
    print(f"正确率变化: {baseline_correct / baseline_total * 100:.2f}% → {practice_correct / practice_total * 100:.2f}% ({accuracy_improvement * 100:+.2f}%)")
    
    if improvement > 0:
        print(f"\n[改进] 训练带来了改进！增加了 {improvement} 个正确的 rollouts")
    elif improvement < 0:
        print(f"\n[退化] 训练后正确数量减少了 {abs(improvement)} 个")
    else:
        print(f"\n[持平] 训练前后正确数量相同")
    
    print("\n" + "=" * 80)
    print()


if __name__ == "__main__":
    import sys
    
    report_file = "完整对比报告_含所有rollouts.md"
    if len(sys.argv) > 1:
        report_file = sys.argv[1]
    
    analyze_report(report_file)

