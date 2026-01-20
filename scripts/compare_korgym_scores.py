#!/usr/bin/env python3
"""
对比 KORGym 游戏评估结果
支持多种游戏类型，自动识别游戏并使用对应的论文基准

Usage:
    python scripts/compare_korgym_scores.py \
        workspace/korgym_eval/baseline.json \
        workspace/korgym_eval/enhanced.json
"""

import argparse
import json
from pathlib import Path
from typing import List, Dict, Optional


# 各游戏的论文基准分数（来自 KORGym 论文）
PAPER_SCORES = {
    'Word Problem': {
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
    },
    'Alphabetical Sorting': {
        # 如果有论文数据，在这里添加
        # 目前为空，只对比自己的结果
    },
    # 可以继续添加其他游戏的论文分数
}

# 游戏名称映射（处理不同的命名方式）
GAME_NAME_MAPPING = {
    '8-word_puzzle': 'Word Problem',
    'word_puzzle': 'Word Problem',
    'Word Problem': 'Word Problem',
    '22-alphabetical_sorting': 'Alphabetical Sorting',
    'alphabetical_sorting': 'Alphabetical Sorting',
    'Alphabetical Sorting': 'Alphabetical Sorting',
}


def detect_game_type(result: Dict) -> Optional[str]:
    """从评估结果中检测游戏类型"""
    # 尝试从不同字段检测
    game_hints = [
        result.get('game_name', ''),
        result.get('dataset_name', ''),
        result.get('exp_id', ''),
        str(result.get('detailed_results', [{}])[0].get('seed', '') if result.get('detailed_results') else ''),
    ]
    
    for hint in game_hints:
        hint_lower = hint.lower()
        if 'word_puzzle' in hint_lower or 'word problem' in hint_lower:
            return 'Word Problem'
        elif 'alphabetical' in hint_lower or '22-alphabetical' in hint_lower:
            return 'Alphabetical Sorting'
    
    return None


def load_result(json_path: str) -> Dict:
    """加载评估结果"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 规范化字段名
    if 'average_score' in data and 'avg_score' not in data:
        data['avg_score'] = data['average_score']
    elif 'avg_score' in data and 'average_score' not in data:
        data['average_score'] = data['avg_score']
    
    return data


def print_comparison(results: List[Dict], game_type: str):
    """打印对比结果"""
    
    print("\n" + "=" * 80)
    print(f"  {game_type} - Score Comparison")
    print("=" * 80)
    print()
    
    # 打印你的结果
    print("📊 Your Results:")
    print(f"{'Experiment':<50} {'Score':>10} {'Games':>10}")
    print("-" * 80)
    
    for result in results:
        score = result.get('avg_score') or result.get('average_score', 0)
        exp_name = Path(result.get('exp_id', 'Unknown')).stem
        num_games = result.get('num_games', 'N/A')
        
        print(f"{exp_name:<50} {score:>10.4f} {num_games:>10}")
    
    print()
    
    # 如果有多个结果，显示提升
    if len(results) > 1:
        baseline = results[0].get('avg_score') or results[0].get('average_score', 0)
        enhanced = results[-1].get('avg_score') or results[-1].get('average_score', 0)
        improvement = enhanced - baseline
        improvement_pct = (improvement / baseline * 100) if baseline > 0 else 0
        
        print("📈 Improvement:")
        print(f"  Baseline:    {baseline:.4f}")
        print(f"  Enhanced:    {enhanced:.4f}")
        print(f"  Improvement: {improvement:+.4f} ({improvement_pct:+.1f}%)")
        print()
    
    # 显示详细统计
    print("📉 Detailed Statistics:")
    print(f"{'Experiment':<50} {'Mean':>8} {'Std':>8} {'Min':>8} {'Max':>8} {'Success%':>10}")
    print("-" * 80)
    for result in results:
        exp_name = Path(result.get('exp_id', 'Unknown')).stem
        mean = result.get('avg_score') or result.get('average_score', 0)
        std = result.get('std_score', 0)
        min_score = result.get('min_score', 0)
        max_score = result.get('max_score', 0)
        success_rate = result.get('success_rate', 0) * 100
        
        print(f"{exp_name:<50} {mean:>8.4f} {std:>8.4f} {min_score:>8.4f} {max_score:>8.4f} {success_rate:>9.1f}%")
    print()
    
    # 如果有论文基准，显示排名
    paper_scores = PAPER_SCORES.get(game_type, {})
    if paper_scores:
        print(f"📖 Paper Benchmark Comparison ({game_type}):")
        print(f"{'Model':<50} {'Score':>10}")
        print("-" * 80)
        
        # 合并你的结果和论文结果
        all_scores = []
        for result in results:
            score = result.get('avg_score') or result.get('average_score', 0)
            exp_name = "→ " + Path(result.get('exp_id', 'Your Model')).stem
            all_scores.append((exp_name, score, True))
        
        for model, score in paper_scores.items():
            all_scores.append((model, score, False))
        
        # 按分数降序排列
        all_scores.sort(key=lambda x: x[1], reverse=True)
        
        # 打印排名
        for i, (model, score, is_yours) in enumerate(all_scores, 1):
            if is_yours:
                print(f"{i:2d}. {model:<48} {score:>10.4f} ⭐")
            else:
                print(f"{i:2d}. {model:<48} {score:>10.4f}")
        
        print()
        
        # 统计你的排名
        for result in results:
            score = result.get('avg_score') or result.get('average_score', 0)
            exp_name = Path(result.get('exp_id', 'Unknown')).stem
            rank = sum(1 for _, s, _ in all_scores if s > score) + 1
            total = len(all_scores)
            better_than = sum(1 for _, s, is_yours in all_scores 
                            if not is_yours and s < score)
            total_paper = sum(1 for _, _, is_yours in all_scores if not is_yours)
            
            print(f"  {exp_name}: Rank {rank}/{total} (better than {better_than}/{total_paper} paper models)")
        
        print("=" * 80)
    else:
        print(f"ℹ️  No paper benchmark data available for {game_type}")
        print(f"   Only showing comparison between your experiments")
        print("=" * 80)
    
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Compare KORGym evaluation results with optional paper benchmarks"
    )
    parser.add_argument(
        'results',
        nargs='+',
        help='Paths to result JSON files (e.g., baseline.json enhanced.json)'
    )
    parser.add_argument(
        '--game-type',
        type=str,
        default=None,
        help='Manually specify game type (e.g., "Word Problem", "Alphabetical Sorting")'
    )
    
    args = parser.parse_args()
    
    # 加载所有结果
    results = []
    for path in args.results:
        try:
            result = load_result(path)
            results.append(result)
        except Exception as e:
            print(f"❌ Error loading {path}: {e}")
            continue
    
    if not results:
        print("❌ No valid results loaded")
        return
    
    # 检测游戏类型
    if args.game_type:
        game_type = args.game_type
    else:
        game_type = detect_game_type(results[0])
        if not game_type:
            game_type = "Unknown Game"
            print(f"⚠️  Could not auto-detect game type. Use --game-type to specify.")
    
    print(f"\n🎮 Detected Game Type: {game_type}")
    
    # 打印对比
    print_comparison(results, game_type)


if __name__ == "__main__":
    main()








