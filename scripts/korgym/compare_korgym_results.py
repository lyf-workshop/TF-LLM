#!/usr/bin/env python3
"""
Compare KORGym baseline vs enhanced results.

Usage:
    python scripts/compare_korgym_results.py \
        --baseline word_puzzle_baseline_eval \
        --enhanced word_puzzle_enhanced_eval
"""

import argparse
import json
from pathlib import Path

from utu.db import EvaluationSample
from utu.utils import SQLModelUtils


def get_eval_results(exp_id: str):
    """Get evaluation results from database."""
    db = SQLModelUtils.create_session()
    try:
        from sqlmodel import select
        statement = select(EvaluationSample).where(EvaluationSample.exp_id == exp_id)
        results = db.exec(statement).all()
        
        if not results:
            print(f"  ⚠ 未找到实验: {exp_id}")
            return None
        
        # Calculate statistics
        total = len(results)
        success = sum(1 for r in results if r.correct)
        
        # Extract scores from meta field
        scores = []
        for r in results:
            if r.meta and 'score' in r.meta:
                scores.append(r.meta['score'])
            elif r.reward is not None:
                scores.append(r.reward * 100)  # Convert back to 0-100 scale
        
        return {
            'exp_id': exp_id,
            'total': total,
            'success': success,
            'success_rate': success / total * 100 if total > 0 else 0,
            'avg_score': sum(scores) / len(scores) if scores else 0,
            'max_score': max(scores) if scores else 0,
            'min_score': min(scores) if scores else 0,
        }
    finally:
        db.close()


def print_comparison(baseline_stats, enhanced_stats):
    """Print comparison table."""
    
    print("\n" + "="*70)
    print("  对比分析结果")
    print("="*70 + "\n")
    
    # Basic stats table
    print(f"{'指标':<20} {'基线 (无经验)':<20} {'增强 (有经验)':<20} {'提升':<10}")
    print("-"*70)
    
    # Success rate
    baseline_sr = baseline_stats['success_rate']
    enhanced_sr = enhanced_stats['success_rate']
    improvement_sr = enhanced_sr - baseline_sr
    print(f"{'成功率':<20} {baseline_sr:>18.1f}% {enhanced_sr:>18.1f}% {improvement_sr:>+8.1f}%")
    
    # Average score
    baseline_avg = baseline_stats['avg_score']
    enhanced_avg = enhanced_stats['avg_score']
    improvement_avg = enhanced_avg - baseline_avg
    improvement_pct = (improvement_avg / baseline_avg * 100) if baseline_avg > 0 else 0
    print(f"{'平均得分':<20} {baseline_avg:>20.2f} {enhanced_avg:>20.2f} {improvement_pct:>+8.1f}%")
    
    # Max score
    print(f"{'最高得分':<20} {baseline_stats['max_score']:>20.2f} {enhanced_stats['max_score']:>20.2f}")
    
    # Total games
    print(f"{'评估局数':<20} {baseline_stats['total']:>20} {enhanced_stats['total']:>20}")
    
    print("-"*70)
    
    # Summary
    print("\n📊 总结:")
    print(f"  • 成功率提升: {improvement_sr:+.1f} 百分点")
    print(f"  • 平均得分提升: {improvement_pct:+.1f}%")
    
    if improvement_sr > 0:
        print(f"\n  ✅ 分层经验学习显著提升了 Agent 性能！")
    elif improvement_sr < 0:
        print(f"\n  ⚠ 性能下降，可能需要检查经验质量或训练参数")
    else:
        print(f"\n  → 性能持平，可能需要更多训练数据")
    
    print("="*70 + "\n")


def load_experiences(exp_path: str):
    """Load and display experience statistics."""
    if not Path(exp_path).exists():
        print(f"  ⚠ 经验文件不存在: {exp_path}")
        return
    
    with open(exp_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    l0_count = len(data.get('l0_experiences', []))
    l1_count = len(data.get('l1_experiences', []))
    l2_count = len(data.get('l2_experiences', []))
    
    print("\n📚 生成的经验统计:")
    print(f"  • L0 (案例级): {l0_count} 个")
    print(f"  • L1 (模式级): {l1_count} 个")
    print(f"  • L2 (元策略级): {l2_count} 个")
    print(f"  • 总计: {l0_count + l1_count + l2_count} 条经验")
    
    # Show sample experiences
    if l2_count > 0:
        print("\n💡 L2 元策略示例:")
        for i, exp in enumerate(data['l2_experiences'][:2], 1):
            content = exp['content'][:150] + "..." if len(exp['content']) > 150 else exp['content']
            print(f"  {i}. {content}")
    
    if l1_count > 0:
        print("\n🧩 L1 模式示例:")
        for i, exp in enumerate(data['l1_experiences'][:2], 1):
            content = exp['content'][:150] + "..." if len(exp['content']) > 150 else exp['content']
            print(f"  {i}. {content}")


def main():
    parser = argparse.ArgumentParser(description="Compare KORGym baseline vs enhanced results")
    parser.add_argument('--baseline', type=str, required=True, help='Baseline experiment ID')
    parser.add_argument('--enhanced', type=str, required=True, help='Enhanced experiment ID')
    parser.add_argument('--exp_file', type=str, 
                       default='workspace/hierarchical_experiences/word_puzzle_exp.json',
                       help='Experience file path')
    
    args = parser.parse_args()
    
    print("\n正在从数据库加载结果...")
    
    # Get results
    baseline_stats = get_eval_results(args.baseline)
    enhanced_stats = get_eval_results(args.enhanced)
    
    if baseline_stats is None or enhanced_stats is None:
        print("\n❌ 无法加载实验结果，请检查实验 ID")
        return 1
    
    # Print comparison
    print_comparison(baseline_stats, enhanced_stats)
    
    # Show experiences
    if Path(args.exp_file).exists():
        load_experiences(args.exp_file)
    
    return 0


if __name__ == "__main__":
    exit(main())

