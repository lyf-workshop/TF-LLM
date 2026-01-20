#!/usr/bin/env python3
"""
查看实际实验中的错误分析信息

从数据库中读取实际的实验数据，查看增强验证器返回的错误信息。
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlmodel import select
from utu.db import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def print_section(title: str, width: int = 80):
    """打印分节标题"""
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width + "\n")


def view_error_analysis_for_exp(exp_id: str, limit: int = 10, show_correct: bool = False):
    """
    查看指定实验的错误分析信息
    
    Args:
        exp_id: 实验ID
        limit: 最多显示多少个样本
        show_correct: 是否也显示正确答案的错误分析（通常应该是None）
    """
    print_section(f"查看实验 {exp_id} 的错误分析信息")
    
    with SQLModelUtils.create_session() as session:
        # 获取所有样本
        query = select(EvaluationSample).where(
            EvaluationSample.exp_id == exp_id
        ).order_by(EvaluationSample.dataset_index)
        
        samples = list(session.exec(query))
        
        if not samples:
            print(f"❌ 未找到实验数据 (exp_id: {exp_id})")
            return
        
        print(f"总样本数: {len(samples)}")
        
        # 统计
        total_samples = len(samples)
        samples_with_reasoning = [s for s in samples if s.reasoning]
        samples_without_reasoning = [s for s in samples if not s.reasoning]
        correct_samples = [s for s in samples if s.reward and s.reward >= 1.0]
        incorrect_samples = [s for s in samples if s.reward and s.reward < 1.0]
        
        print(f"  有 reasoning 的样本: {len(samples_with_reasoning)}")
        print(f"  没有 reasoning 的样本: {len(samples_without_reasoning)}")
        print(f"  正确答案: {len(correct_samples)}")
        print(f"  错误答案: {len(incorrect_samples)}")
        
        # 分析错误答案的 reasoning 内容
        print_section("错误答案的 Reasoning 内容分析")
        
        incorrect_with_reasoning = [s for s in incorrect_samples if s.reasoning]
        print(f"错误答案中有 reasoning 的样本: {len(incorrect_with_reasoning)}")
        
        if not incorrect_with_reasoning:
            print("\n⚠️  没有找到错误答案的 reasoning 信息")
            print("   可能的原因:")
            print("   1. 使用的是基本验证器（logic.py），不是增强验证器")
            print("   2. 错误分析被禁用了（enable_error_analysis=False）")
            print("   3. LogicErrorAnalyzer 不可用或出错")
            return
        
        # 显示前几个样本的详细信息
        print(f"\n显示前 {min(limit, len(incorrect_with_reasoning))} 个错误答案的详细信息:\n")
        
        for i, sample in enumerate(incorrect_with_reasoning[:limit], 1):
            print(f"\n{'='*80}")
            print(f"样本 {i} (dataset_index: {sample.dataset_index})")
            print(f"{'='*80}")
            
            print(f"\n【Reward】: {sample.reward}")
            print(f"\n【Reasoning 长度】: {len(sample.reasoning) if sample.reasoning else 0} 字符")
            print(f"\n【Reasoning 内容】:")
            print("-" * 80)
            if sample.reasoning:
                # 显示前500个字符，如果太长
                reasoning_display = sample.reasoning
                if len(reasoning_display) > 500:
                    reasoning_display = reasoning_display[:500] + "\n... (内容过长，已截断)"
                print(reasoning_display)
            else:
                print("(无)")
            print("-" * 80)
            
            # 分析 reasoning 内容
            if sample.reasoning:
                reasoning_lower = sample.reasoning.lower()
                error_types = []
                if "constraint violation" in reasoning_lower or "约束违反" in sample.reasoning:
                    error_types.append("约束违反")
                if "contradiction" in reasoning_lower or "矛盾" in sample.reasoning:
                    error_types.append("矛盾")
                if "assignment" in reasoning_lower or "赋值" in sample.reasoning:
                    error_types.append("赋值错误")
                if "incomplete" in reasoning_lower or "不完整" in sample.reasoning:
                    error_types.append("推理不完整")
                if "inconsistenc" in reasoning_lower or "不一致" in sample.reasoning:
                    error_types.append("逻辑不一致")
                
                if error_types:
                    print(f"\n【检测到的错误类型】: {', '.join(error_types)}")
                else:
                    print(f"\n【检测到的错误类型】: 未识别到特定错误类型")
            
            # 显示答案（如果太长就截断）
            if sample.response:
                response_preview = sample.response[:200] + "..." if len(sample.response) > 200 else sample.response
                print(f"\n【Response 预览】:")
                print("-" * 80)
                print(response_preview)
                print("-" * 80)
        
        # 统计 reasoning 长度分布
        print_section("Reasoning 长度统计")
        if incorrect_with_reasoning:
            lengths = [len(s.reasoning) for s in incorrect_with_reasoning if s.reasoning]
            if lengths:
                print(f"  最短: {min(lengths)} 字符")
                print(f"  最长: {max(lengths)} 字符")
                print(f"  平均: {sum(lengths) / len(lengths):.1f} 字符")
                print(f"  中位数: {sorted(lengths)[len(lengths)//2]} 字符")
                
                # 长度分布
                very_short = sum(1 for l in lengths if l < 50)
                short = sum(1 for l in lengths if 50 <= l < 200)
                medium = sum(1 for l in lengths if 200 <= l < 500)
                long_text = sum(1 for l in lengths if l >= 500)
                
                print(f"\n  长度分布:")
                print(f"    很短 (<50): {very_short} ({very_short/len(lengths)*100:.1f}%)")
                print(f"    短 (50-200): {short} ({short/len(lengths)*100:.1f}%)")
                print(f"    中 (200-500): {medium} ({medium/len(lengths)*100:.1f}%)")
                print(f"    长 (>=500): {long_text} ({long_text/len(lengths)*100:.1f}%)")
        
        # 检查正确答案是否有 reasoning（不应该有）
        print_section("检查正确答案的 Reasoning（应该为 None）")
        correct_with_reasoning = [s for s in correct_samples if s.reasoning]
        if correct_with_reasoning:
            print(f"⚠️  警告: 发现 {len(correct_with_reasoning)} 个正确答案有 reasoning 信息")
            print("   这不应该发生！正确答案不应该触发错误分析。")
            print("   可能的问题:")
            print("   1. 验证逻辑有bug")
            print("   2. 数据被手动修改过")
        else:
            print("✓ 所有正确答案都没有 reasoning 信息（正确）")


def compare_two_experiments(exp_id_basic: str, exp_id_enhanced: str, limit: int = 5):
    """对比两个实验（一个用基本验证器，一个用增强验证器）"""
    print_section(f"对比实验: {exp_id_basic} (基本) vs {exp_id_enhanced} (增强)")
    
    with SQLModelUtils.create_session() as session:
        # 获取两个实验的样本
        samples_basic = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == exp_id_basic
            ).order_by(EvaluationSample.dataset_index)
        ))
        
        samples_enhanced = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == exp_id_enhanced
            ).order_by(EvaluationSample.dataset_index)
        ))
        
        if not samples_basic or not samples_enhanced:
            print("❌ 未找到实验数据")
            return
        
        # 按 dataset_index 匹配样本
        basic_by_index = {s.dataset_index: s for s in samples_basic}
        enhanced_by_index = {s.dataset_index: s for s in samples_enhanced}
        
        common_indices = set(basic_by_index.keys()) & set(enhanced_by_index.keys())
        print(f"共同样本数: {len(common_indices)}")
        
        # 对比前几个错误答案
        incorrect_basic = [s for s in samples_basic if s.reward and s.reward < 1.0]
        incorrect_enhanced = [s for s in samples_enhanced if s.reward and s.reward < 1.0]
        
        print(f"\n基本验证器错误答案数: {len(incorrect_basic)}")
        print(f"增强验证器错误答案数: {len(incorrect_enhanced)}")
        
        # 显示对比
        print(f"\n显示前 {limit} 个共同错误答案的对比:\n")
        
        count = 0
        for idx in sorted(common_indices):
            if count >= limit:
                break
            
            basic_sample = basic_by_index.get(idx)
            enhanced_sample = enhanced_by_index.get(idx)
            
            if not basic_sample or not enhanced_sample:
                continue
            
            if (basic_sample.reward and basic_sample.reward < 1.0 and
                enhanced_sample.reward and enhanced_sample.reward < 1.0):
                
                count += 1
                print(f"\n{'='*80}")
                print(f"样本 {count} (dataset_index: {idx})")
                print(f"{'='*80}")
                
                print(f"\n【基本验证器】")
                print(f"  Reward: {basic_sample.reward}")
                print(f"  Reasoning: {basic_sample.reasoning or '(无)'}")
                
                print(f"\n【增强验证器】")
                print(f"  Reward: {enhanced_sample.reward}")
                print(f"  Reasoning 长度: {len(enhanced_sample.reasoning) if enhanced_sample.reasoning else 0} 字符")
                if enhanced_sample.reasoning:
                    reasoning_preview = enhanced_sample.reasoning[:300]
                    if len(enhanced_sample.reasoning) > 300:
                        reasoning_preview += "..."
                    print(f"  Reasoning 内容:")
                    print("  " + "-" * 76)
                    for line in reasoning_preview.split('\n'):
                        print(f"  {line}")
                    print("  " + "-" * 76)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="查看实际实验中的错误分析信息")
    parser.add_argument("exp_id", help="实验ID")
    parser.add_argument("--limit", type=int, default=10, help="最多显示多少个样本")
    parser.add_argument("--show-correct", action="store_true", help="也显示正确答案")
    parser.add_argument("--compare", help="对比另一个实验ID（基本验证器）")
    
    args = parser.parse_args()
    
    if args.compare:
        compare_two_experiments(args.compare, args.exp_id, args.limit)
    else:
        view_error_analysis_for_exp(args.exp_id, args.limit, args.show_correct)


if __name__ == "__main__":
    main()







































































