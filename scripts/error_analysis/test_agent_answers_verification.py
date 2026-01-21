#!/usr/bin/env python3
"""
测试 logic.py 验证器对特定经验库生成的答案的判断能力

此脚本从数据库中提取实际的 agent 答案，然后测试验证器的判断是否正确
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.db import EvaluationSample, DatasetSample
from utu.practice.verify.logic import verify_func
from utu.utils.sqlmodel_utils import SQLModelUtils
from sqlmodel import Session, select


def get_experiment_samples(exp_id: str, limit: int = 50) -> List[EvaluationSample]:
    """从数据库中获取指定实验的样本"""
    engine = SQLModelUtils.get_engine()
    
    with Session(engine) as session:
        stmt = select(EvaluationSample).where(
            EvaluationSample.exp_id == exp_id
        ).limit(limit)
        
        samples = session.exec(stmt).all()
        return list(samples)


def get_experiment_info(exp_id: str) -> Dict[str, Any]:
    """获取实验的基本信息（从样本统计）"""
    engine = SQLModelUtils.get_engine()
    
    with Session(engine) as session:
        stmt = select(EvaluationSample).where(
            EvaluationSample.exp_id == exp_id
        )
        
        samples = session.exec(stmt).all()
        if samples:
            total = len(samples)
            correct = sum(1 for s in samples if s.reward >= 1.0)
            avg_reward = sum(s.reward for s in samples) / total if total > 0 else 0
            
            # 获取第一个样本的创建时间作为参考
            created_at = samples[0].created_at if hasattr(samples[0], 'created_at') else None
            
            return {
                "exp_id": exp_id,
                "agent_config": "N/A",  # EvaluationSample 表中没有这个字段
                "total_count": total,
                "correct_count": correct,
                "accuracy": correct / total if total > 0 else 0,
                "avg_reward": avg_reward,
                "created_at": created_at
            }
    return None


def re_verify_samples(samples: List[EvaluationSample]) -> Dict[str, Any]:
    """重新验证所有样本"""
    results = {
        "total": len(samples),
        "original_correct": 0,
        "reverify_correct": 0,
        "match_count": 0,
        "mismatch_cases": [],
        "verification_details": []
    }
    
    for i, db_sample in enumerate(samples, 1):
        # 数据库中的 EvaluationSample 可以直接用于验证
        # 原始判断
        original_correct = db_sample.reward >= 1.0
        
        # 重新验证
        try:
            verify_result = verify_func(db_sample)
            reverify_correct = verify_result["reward"] >= 1.0
        except Exception as e:
            print(f"⚠️  样本 {i} 验证失败: {e}")
            import traceback
            traceback.print_exc()
            verify_result = {"reward": 0.0, "reasoning": f"Verification error: {e}"}
            reverify_correct = False
        
        # 统计
        if original_correct:
            results["original_correct"] += 1
        if reverify_correct:
            results["reverify_correct"] += 1
        
        # 检查是否匹配
        if original_correct == reverify_correct:
            results["match_count"] += 1
        else:
            # 记录不匹配的案例
            question_id = getattr(db_sample, 'question_id', 'N/A')
            results["mismatch_cases"].append({
                "sample_id": i,
                "question_id": question_id,
                "original_reward": db_sample.reward,
                "reverify_reward": verify_result["reward"],
                "original_correct": original_correct,
                "reverify_correct": reverify_correct,
                "question": db_sample.raw_question[:200] if db_sample.raw_question else "",
                "response": db_sample.response[:300] if db_sample.response else "",
                "ground_truth": db_sample.correct_answer[:200] if db_sample.correct_answer else ""
            })
        
        # 记录详细信息（前10个）
        if i <= 10:
            results["verification_details"].append({
                "sample_id": i,
                "original_reward": db_sample.reward,
                "reverify_reward": verify_result["reward"],
                "match": original_correct == reverify_correct
            })
    
    return results


def print_analysis_report(exp_id: str, exp_info: Dict, results: Dict):
    """打印分析报告"""
    print("\n" + "="*80)
    print(f"验证器测试报告: {exp_id}")
    print("="*80)
    
    # 实验信息
    if exp_info:
        print(f"\n📊 实验信息:")
        print(f"  实验ID: {exp_info['exp_id']}")
        print(f"  Agent配置: {exp_info['agent_config']}")
        print(f"  创建时间: {exp_info['created_at']}")
        print(f"  总样本数: {exp_info['total_count']}")
        print(f"  原始正确数: {exp_info['correct_count']}")
        print(f"  原始正确率: {exp_info['accuracy']:.2%}")
        print(f"  平均Reward: {exp_info['avg_reward']:.4f}")
    
    # 重新验证结果
    print(f"\n🔍 重新验证结果:")
    print(f"  测试样本数: {results['total']}")
    print(f"  原始判断为正确: {results['original_correct']} ({results['original_correct']/results['total']*100:.1f}%)")
    print(f"  重新验证为正确: {results['reverify_correct']} ({results['reverify_correct']/results['total']*100:.1f}%)")
    print(f"  判断一致的样本: {results['match_count']} ({results['match_count']/results['total']*100:.1f}%)")
    print(f"  判断不一致的样本: {len(results['mismatch_cases'])} ({len(results['mismatch_cases'])/results['total']*100:.1f}%)")
    
    # 前10个样本的详细信息
    print(f"\n📋 前10个样本的验证详情:")
    for detail in results["verification_details"]:
        status = "✓" if detail["match"] else "✗"
        print(f"  {status} 样本 {detail['sample_id']}: 原始={detail['original_reward']:.2f}, 重验={detail['reverify_reward']:.2f}")
    
    # 不匹配案例分析
    if results["mismatch_cases"]:
        print(f"\n⚠️  发现 {len(results['mismatch_cases'])} 个判断不一致的案例:")
        
        for i, case in enumerate(results["mismatch_cases"][:5], 1):  # 只显示前5个
            print(f"\n  案例 {i} (样本 {case['sample_id']}):")
            print(f"    原始判断: {'正确' if case['original_correct'] else '错误'} (reward={case['original_reward']:.2f})")
            print(f"    重新验证: {'正确' if case['reverify_correct'] else '错误'} (reward={case['reverify_reward']:.2f})")
            print(f"    问题: {case['question'][:150]}...")
            print(f"    答案: {case['response'][:200]}...")
            print(f"    标准答案: {case['ground_truth'][:150]}...")
        
        if len(results["mismatch_cases"]) > 5:
            print(f"\n  ... 还有 {len(results['mismatch_cases']) - 5} 个不一致案例未显示")
    
    # 结论
    print(f"\n" + "="*80)
    print("🎯 结论:")
    print("="*80)
    
    match_rate = results['match_count'] / results['total'] * 100
    
    if match_rate >= 99:
        print("✅ 验证器工作正常！几乎所有判断都一致。")
    elif match_rate >= 95:
        print("⚠️  验证器基本正常，但存在少量不一致（可能是边界情况）。")
    elif match_rate >= 80:
        print("❌ 验证器存在明显问题！建议检查验证逻辑。")
    else:
        print("🚨 验证器严重异常！大量判断不一致！")
    
    if results['reverify_correct'] != results['original_correct']:
        diff = results['reverify_correct'] - results['original_correct']
        print(f"\n💡 重新验证发现:")
        if diff > 0:
            print(f"   {diff} 个样本原本判断为错误，但重新验证为正确")
            print(f"   这可能意味着原始评估时的验证逻辑有问题")
        else:
            print(f"   {-diff} 个样本原本判断为正确，但重新验证为错误")
            print(f"   这可能意味着当前验证器更严格，或原始答案格式有问题")


def compare_multiple_experiments(exp_ids: List[str], sample_limit: int = 50):
    """对比多个实验的验证结果"""
    print("\n" + "="*80)
    print("多实验对比分析")
    print("="*80)
    
    comparison = []
    
    for exp_id in exp_ids:
        print(f"\n处理实验: {exp_id}...")
        
        exp_info = get_experiment_info(exp_id)
        if not exp_info:
            print(f"  ⚠️  未找到实验 {exp_id}")
            continue
        
        samples = get_experiment_samples(exp_id, limit=sample_limit)
        if not samples:
            print(f"  ⚠️  实验 {exp_id} 没有样本数据")
            continue
        
        print(f"  找到 {len(samples)} 个样本，开始重新验证...")
        results = re_verify_samples(samples)
        
        comparison.append({
            "exp_id": exp_id,
            "agent_config": exp_info.get("agent_config", "N/A"),
            "original_accuracy": exp_info["accuracy"],
            "reverify_accuracy": results["reverify_correct"] / results["total"] if results["total"] > 0 else 0,
            "match_rate": results["match_count"] / results["total"] if results["total"] > 0 else 0,
            "sample_count": results["total"]
        })
    
    # 打印对比表格
    if comparison:
        print("\n" + "="*80)
        print("实验对比结果")
        print("="*80)
        print(f"\n{'实验ID':<45} {'原始正确率':<12} {'重验正确率':<12} {'匹配率':<10} {'样本数':<8}")
        print("-" * 85)
        
        for c in comparison:
            print(f"{c['exp_id']:<45} {c['original_accuracy']:<12.2%} {c['reverify_accuracy']:<12.2%} {c['match_rate']:<10.2%} {c['sample_count']:<8}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="测试验证器对特定经验库生成答案的判断能力")
    parser.add_argument("--exp_id", type=str, help="实验ID")
    parser.add_argument("--exp_ids", nargs="+", help="多个实验ID（用于对比）")
    parser.add_argument("--sample_limit", type=int, default=50, help="测试样本数量限制")
    parser.add_argument("--compare", action="store_true", help="对比多个实验")
    
    args = parser.parse_args()
    
    # 如果没有提供任何参数，使用默认实验
    if not args.exp_id and not args.exp_ids:
        print("未指定实验ID，使用以下默认实验:")
        args.exp_ids = [
            "zebralogic_practice_medium30_1",
            "zebralogic_baseline_medium30"
        ]
        args.compare = True
        print(f"  {', '.join(args.exp_ids)}")
    
    # 单个实验详细分析
    if args.exp_id:
        print(f"\n开始测试实验: {args.exp_id}")
        
        # 获取实验信息
        exp_info = get_experiment_info(args.exp_id)
        if not exp_info:
            print(f"❌ 未找到实验 {args.exp_id}")
            sys.exit(1)
        
        # 获取样本
        samples = get_experiment_samples(args.exp_id, limit=args.sample_limit)
        if not samples:
            print(f"❌ 实验 {args.exp_id} 没有样本数据")
            sys.exit(1)
        
        print(f"找到 {len(samples)} 个样本，开始重新验证...")
        
        # 重新验证
        results = re_verify_samples(samples)
        
        # 打印报告
        print_analysis_report(args.exp_id, exp_info, results)
    
    # 多实验对比
    if args.compare and args.exp_ids:
        compare_multiple_experiments(args.exp_ids, sample_limit=args.sample_limit)
    
    print("\n" + "="*80)
    print("测试完成")
    print("="*80)


if __name__ == "__main__":
    main()

