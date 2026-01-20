#!/usr/bin/env python3
"""
对比多个评估结果与论文的分数

Usage:
    python scripts/compare_paper_scores.py \
        workspace/korgym_paper_aligned/baseline_word_puzzle.json \
        workspace/korgym_paper_aligned/enhanced_word_puzzle.json
"""

import argparse
import json
from pathlib import Path
from typing import List, Dict


# 论文中的分数
PAPER_SCORES = {
    'O1-2024-12-17': 0.960,
    'Gemini-2.5-pro-03-25': 0.900,
    'Claude-3.7-thinking': 0.820,
    'DeepSeek-R1': 0.820,
    'O3-mini': 0.880,
    'Gemini-2.0-Flash-thinking': 0.620,
    'Claude-3.7': 0.580,
    'DeepSeek-v3-0324': 0.460,
    'GPT-4o': 0.420,
    'Doubao-1.5-thinking-pro': 0.600,
    'Gemini-2.0-Flash': 0.340,
    'Doubao-1.5-pro': 0.120,
    'DeepSeek-R1-Distill-Qwen-32B': 0.340,
    'Qwen-Max': 0.480,
    'DeepSeek-R1-Distill-Qwen-7B': 0.020,
}


def load_result(json_path: str) -> Dict:
    """加载评估结果"""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def print_comparison(results: List[Dict]):
    """打印对比结果"""
    
    print("\n" + "=" * 80)
    print("  Word Puzzle Score Comparison (Paper Format)")
    print("=" * 80)
    print()
    
    # 打印你的结果
    print("📊 Your Results:")
    print(f"{'Experiment':<40} {'Score':>10} {'vs Paper':<30}")
    print("-" * 80)
    
    for result in results:
        # Support both formats: 'avg_score' and 'average_score'
        score = result.get('avg_score') or result.get('average_score', 0)
        exp_name = Path(result.get('agent_config', 'Unknown')).stem
        
        # 找到最接近的论文模型
        closest = min(PAPER_SCORES.items(), key=lambda x: abs(x[1] - score))
        comparison = f"≈ {closest[0]}"
        
        print(f"{exp_name:<40} {score:>10.3f} {comparison:<30}")
    
    print()
    
    # 如果有多个结果，显示提升
    if len(results) > 1:
        baseline = results[0].get('avg_score') or results[0].get('average_score', 0)
        enhanced = results[-1].get('avg_score') or results[-1].get('average_score', 0)
        improvement = enhanced - baseline
        improvement_pct = (improvement / baseline * 100) if baseline > 0 else 0
        
        print("📈 Improvement:")
        print(f"  Baseline:    {baseline:.3f}")
        print(f"  Enhanced:    {enhanced:.3f}")
        print(f"  Improvement: +{improvement:.3f} ({improvement_pct:+.1f}%)")
        print()
    
    # 打印论文中的完整排名
    print("📖 Full Paper Ranking (Table 7 - Word Problem):")
    print(f"{'Model':<40} {'Score':>10}")
    print("-" * 80)
    
    # 合并你的结果和论文结果，排序
    all_scores = []
    for result in results:
        score = result.get('avg_score') or result.get('average_score', 0)
        exp_name = "→ " + Path(result.get('agent_config', 'Your Model')).stem
        all_scores.append((exp_name, score, True))  # True 表示是你的结果
    
    for model, score in PAPER_SCORES.items():
        all_scores.append((model, score, False))
    
    # 按分数降序排列
    all_scores.sort(key=lambda x: x[1], reverse=True)
    
    # 打印排名
    for i, (model, score, is_yours) in enumerate(all_scores, 1):
        if is_yours:
            print(f"{i:2d}. {model:<38} {score:>10.3f} ⭐")
        else:
            print(f"{i:2d}. {model:<38} {score:>10.3f}")
    
    print()
    
    # 统计你的排名
    for result in results:
        score = result.get('avg_score') or result.get('average_score', 0)
        rank = sum(1 for _, s, _ in all_scores if s > score) + 1
        total = len(all_scores)
        better_than = sum(1 for _, s, is_yours in all_scores 
                         if not is_yours and score > s)
        
        exp_name = Path(result.get('agent_config', 'Your Model')).stem
        print(f"  {exp_name}: Rank {rank}/{total} "
              f"(better than {better_than}/{len(PAPER_SCORES)} paper models)")
    
    print()
    print("=" * 80)
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Compare evaluation results with paper scores"
    )
    parser.add_argument(
        'result_files',
        nargs='+',
        help='JSON result files to compare'
    )
    
    args = parser.parse_args()
    
    # 加载所有结果
    results = []
    for file_path in args.result_files:
        try:
            result = load_result(file_path)
            results.append(result)
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    if not results:
        print("No valid result files found")
        return
    
    # 打印对比
    print_comparison(results)


if __name__ == "__main__":
    main()

