#!/usr/bin/env python3
"""
分析题目的难度分布
"""

import re
from collections import defaultdict
from pathlib import Path


def analyze_difficulty_distribution(report_file: str, output_file: str):
    """分析题目难度分布"""
    
    print(f"\n{'='*80}")
    print(f"分析题目难度分布")
    print(f"{'='*80}\n")
    
    # 读取报告文件
    with open(report_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取所有题目的正确率数据
    pattern = r'^\| (\d+) \| 32 \| (\d+) \| \d+ \| ([\d.]+)% \|'
    matches = re.findall(pattern, content, re.MULTILINE)
    
    if not matches:
        print("❌ 未找到题目数据")
        return
    
    # 解析数据
    problems = []
    for match in matches:
        problem_id = int(match[0])
        correct_count = int(match[1])
        accuracy = float(match[2])
        problems.append({
            'id': problem_id,
            'correct': correct_count,
            'accuracy': accuracy
        })
    
    # 按正确率排序
    problems_sorted = sorted(problems, key=lambda x: x['accuracy'])
    
    print(f"✅ 成功提取 {len(problems)} 道题目的数据\n")
    
    # 难度分级
    def get_difficulty_level(accuracy):
        if accuracy == 0:
            return "极难 (0%)"
        elif accuracy < 10:
            return "非常难 (0-10%)"
        elif accuracy < 30:
            return "困难 (10-30%)"
        elif accuracy < 50:
            return "中等偏难 (30-50%)"
        elif accuracy < 70:
            return "中等 (50-70%)"
        elif accuracy < 85:
            return "简单 (70-85%)"
        else:
            return "非常简单 (85-100%)"
    
    # 统计各难度等级
    difficulty_stats = defaultdict(list)
    for p in problems:
        level = get_difficulty_level(p['accuracy'])
        difficulty_stats[level].append(p)
    
    # 生成报告
    output_lines = []
    output_lines.append("# 题目难度分布分析\n\n")
    output_lines.append("**实验 ID**: `logic_zebralogic_test_eval`\n\n")
    output_lines.append("---\n\n")
    
    # 总体统计
    total_problems = len(problems)
    avg_accuracy = sum(p['accuracy'] for p in problems) / total_problems
    median_accuracy = problems_sorted[total_problems // 2]['accuracy']
    min_accuracy = problems_sorted[0]['accuracy']
    max_accuracy = problems_sorted[-1]['accuracy']
    
    output_lines.append("## 📊 总体统计\n\n")
    output_lines.append(f"- **总题目数**: {total_problems}\n")
    output_lines.append(f"- **平均正确率**: {avg_accuracy:.2f}%\n")
    output_lines.append(f"- **中位数正确率**: {median_accuracy:.2f}%\n")
    output_lines.append(f"- **最低正确率**: {min_accuracy:.2f}% (题目 {problems_sorted[0]['id']})\n")
    output_lines.append(f"- **最高正确率**: {max_accuracy:.2f}% (题目 {problems_sorted[-1]['id']})\n")
    output_lines.append(f"- **标准差**: {calculate_std([p['accuracy'] for p in problems]):.2f}%\n\n")
    output_lines.append("---\n\n")
    
    # 难度分布统计
    output_lines.append("## 📈 难度分布统计\n\n")
    output_lines.append("| 难度等级 | 题目数量 | 占比 | 题目编号 |\n")
    output_lines.append("|---------|---------|------|---------|\n")
    
    # 按难度等级排序（从易到难）
    difficulty_order = [
        "非常简单 (85-100%)",
        "简单 (70-85%)",
        "中等 (50-70%)",
        "中等偏难 (30-50%)",
        "困难 (10-30%)",
        "非常难 (0-10%)",
        "极难 (0%)"
    ]
    
    for level in difficulty_order:
        if level in difficulty_stats:
            problems_in_level = difficulty_stats[level]
            count = len(problems_in_level)
            percentage = count / total_problems * 100
            problem_ids = ', '.join(str(p['id']) for p in sorted(problems_in_level, key=lambda x: x['id']))
            output_lines.append(f"| {level} | {count} | {percentage:.1f}% | {problem_ids} |\n")
    
    output_lines.append("\n---\n\n")
    
    # 详细列表（按正确率排序）
    output_lines.append("## 📋 所有题目按难度排序（从易到难）\n\n")
    output_lines.append("| 排名 | 题目编号 | 正确数/总数 | 正确率 | 难度等级 |\n")
    output_lines.append("|------|---------|------------|--------|----------|\n")
    
    for rank, p in enumerate(problems_sorted, 1):
        level = get_difficulty_level(p['accuracy'])
        output_lines.append(f"| {rank} | {p['id']} | {p['correct']}/32 | {p['accuracy']:.2f}% | {level} |\n")
    
    output_lines.append("\n---\n\n")
    
    # 难度分布可视化（ASCII图表）
    output_lines.append("## 📊 难度分布可视化\n\n")
    output_lines.append("```\n")
    output_lines.append("正确率分布（每10%一个区间）:\n")
    output_lines.append("\n")
    
    # 统计各区间
    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    bin_counts = [0] * (len(bins) - 1)
    bin_labels = []
    
    for i in range(len(bins) - 1):
        start = bins[i]
        end = bins[i + 1]
        if i == len(bins) - 2:
            label = f"{start}%"
        else:
            label = f"{start}-{end}%"
        bin_labels.append(label)
        
        for p in problems:
            if start <= p['accuracy'] < end or (i == len(bins) - 2 and p['accuracy'] == 100):
                bin_counts[i] += 1
    
    # 绘制条形图
    max_count = max(bin_counts) if bin_counts else 1
    for i, (label, count) in enumerate(zip(bin_labels, bin_counts)):
        bar_length = int(count / max_count * 50) if max_count > 0 else 0
        bar = '█' * bar_length
        output_lines.append(f"{label:8s} │{bar} {count}\n")
    
    output_lines.append("```\n\n")
    output_lines.append("---\n\n")
    
    # 关键发现
    output_lines.append("## 🔍 关键发现\n\n")
    
    # 统计各难度区间的题目
    very_easy = [p for p in problems if p['accuracy'] >= 85]
    easy = [p for p in problems if 70 <= p['accuracy'] < 85]
    medium = [p for p in problems if 50 <= p['accuracy'] < 70]
    medium_hard = [p for p in problems if 30 <= p['accuracy'] < 50]
    hard = [p for p in problems if 10 <= p['accuracy'] < 30]
    very_hard = [p for p in problems if 0 < p['accuracy'] < 10]
    impossible = [p for p in problems if p['accuracy'] == 0]
    
    output_lines.append(f"### 难度分布特点\n\n")
    output_lines.append(f"- **非常简单** (≥85%): {len(very_easy)} 道题目\n")
    if very_easy:
        output_lines.append(f"  - 题目编号: {', '.join(str(p['id']) for p in sorted(very_easy, key=lambda x: x['id']))}\n")
    
    output_lines.append(f"- **简单** (70-85%): {len(easy)} 道题目\n")
    if easy:
        output_lines.append(f"  - 题目编号: {', '.join(str(p['id']) for p in sorted(easy, key=lambda x: x['id']))}\n")
    
    output_lines.append(f"- **中等** (50-70%): {len(medium)} 道题目\n")
    if medium:
        output_lines.append(f"  - 题目编号: {', '.join(str(p['id']) for p in sorted(medium, key=lambda x: x['id']))}\n")
    
    output_lines.append(f"- **中等偏难** (30-50%): {len(medium_hard)} 道题目\n")
    if medium_hard:
        output_lines.append(f"  - 题目编号: {', '.join(str(p['id']) for p in sorted(medium_hard, key=lambda x: x['id']))}\n")
    
    output_lines.append(f"- **困难** (10-30%): {len(hard)} 道题目\n")
    if hard:
        output_lines.append(f"  - 题目编号: {', '.join(str(p['id']) for p in sorted(hard, key=lambda x: x['id']))}\n")
    
    output_lines.append(f"- **非常难** (0-10%): {len(very_hard)} 道题目\n")
    if very_hard:
        output_lines.append(f"  - 题目编号: {', '.join(str(p['id']) for p in sorted(very_hard, key=lambda x: x['id']))}\n")
    
    output_lines.append(f"- **极难** (0%): {len(impossible)} 道题目\n")
    if impossible:
        output_lines.append(f"  - 题目编号: {', '.join(str(p['id']) for p in sorted(impossible, key=lambda x: x['id']))}\n")
    
    output_lines.append("\n")
    
    # 分析
    output_lines.append("### 分布特征分析\n\n")
    
    if len(impossible) > 0:
        output_lines.append(f"⚠️ **存在无法解决的题目**: {len(impossible)} 道题目（题目 {', '.join(str(p['id']) for p in impossible)}）在32次尝试中全部失败。\n\n")
    
    if len(very_easy) + len(easy) > len(medium) + len(medium_hard) + len(hard) + len(very_hard) + len(impossible):
        output_lines.append("✅ **整体偏易**: 简单和非常简单的题目数量多于困难题目。\n\n")
    elif len(medium) + len(medium_hard) + len(hard) + len(very_hard) + len(impossible) > len(very_easy) + len(easy):
        output_lines.append("⚠️ **整体偏难**: 中等难度及以上的题目数量多于简单题目。\n\n")
    else:
        output_lines.append("📊 **难度分布相对均衡**: 简单和困难题目数量相近。\n\n")
    
    # 计算难度集中度
    if avg_accuracy < 50:
        output_lines.append(f"📉 **平均正确率较低** ({avg_accuracy:.2f}%)，说明整体题目难度较高。\n\n")
    elif avg_accuracy > 60:
        output_lines.append(f"📈 **平均正确率较高** ({avg_accuracy:.2f}%)，说明整体题目难度较低。\n\n")
    else:
        output_lines.append(f"📊 **平均正确率中等** ({avg_accuracy:.2f}%)，难度分布合理。\n\n")
    
    # 保存报告
    output_text = ''.join(output_lines)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(output_text)
    
    print(f"✅ 难度分布分析报告已生成: {output_file}")


def calculate_std(values):
    """计算标准差"""
    if len(values) == 0:
        return 0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return variance ** 0.5


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="分析题目难度分布")
    parser.add_argument(
        "--input",
        type=str,
        default="baseline_每题正确答案数统计.md",
        help="输入报告文件"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="题目难度分布分析.md",
        help="输出文件"
    )
    
    args = parser.parse_args()
    
    analyze_difficulty_distribution(args.input, args.output)















































































