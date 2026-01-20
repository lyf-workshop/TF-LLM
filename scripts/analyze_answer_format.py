#!/usr/bin/env python3
"""
分析答案格式问题 - 诊断验证器是否因为格式问题导致判断错误

这个脚本会：
1. 提取实际答案和标准答案
2. 显示答案格式
3. 测试验证器的解析过程
4. 诊断格式问题
"""

import json
import re
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.db import EvaluationSample
from utu.practice.verify.logic import verify_func
from utu.utils.sqlmodel_utils import SQLModelUtils
from sqlmodel import Session, select


def _try_parse_dict_or_json(text: str) -> any:
    """尝试解析为 dict 或 JSON"""
    if not text:
        return None
    
    # 先尝试 JSON
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # 尝试 Python dict (单引号)
    try:
        # 将单引号替换为双引号
        json_text = text.replace("'", '"')
        return json.loads(json_text)
    except (json.JSONDecodeError, ValueError):
        pass
    
    return None


def extract_answer_debug(response: str) -> tuple[str, dict]:
    """
    调试版的答案提取函数，返回提取过程的详细信息
    
    Returns:
        (extracted_answer, debug_info)
    """
    debug_info = {
        "original_response": response[:500],
        "steps": []
    }
    
    if not response:
        debug_info["steps"].append("响应为空")
        return "", debug_info
    
    # Step 1: 查找 <answer> 标签
    answer_pattern = r'<answer>(.*?)</answer>'
    answer_match = re.search(answer_pattern, response, re.DOTALL | re.IGNORECASE)
    
    if answer_match:
        answer_text = answer_match.group(1).strip()
        debug_info["steps"].append(f"找到 <answer> 标签，内容长度: {len(answer_text)}")
        debug_info["answer_text"] = answer_text[:300]
    else:
        debug_info["steps"].append("未找到 <answer> 标签，使用完整响应")
        answer_text = response
        debug_info["answer_text"] = answer_text[:300]
    
    # Step 2: 提取 \boxed{} 内容
    boxed_pattern = r'\\boxed\{(.*?)\}'
    boxed_match = re.search(boxed_pattern, answer_text, re.DOTALL)
    
    if boxed_match:
        extracted = boxed_match.group(1).strip()
        debug_info["steps"].append(f"找到 \\boxed{{}} 格式，内容: {extracted[:100]}")
        debug_info["extracted_from_boxed"] = extracted[:200]
        answer_text = extracted
    else:
        debug_info["steps"].append("未找到 \\boxed{} 格式")
    
    # Step 3: 尝试解析 JSON
    # 移除可能的 markdown 代码块
    if answer_text.startswith('```'):
        debug_info["steps"].append("发现 markdown 代码块，尝试移除")
        answer_text = re.sub(r'^```(?:json)?\s*\n', '', answer_text)
        answer_text = re.sub(r'\n```\s*$', '', answer_text)
    
    parsed = _try_parse_dict_or_json(answer_text)
    if parsed is not None:
        debug_info["steps"].append(f"成功解析为 JSON/dict，类型: {type(parsed).__name__}")
        debug_info["parsed_json"] = str(parsed)[:200]
        return json.dumps(parsed, ensure_ascii=False), debug_info
    else:
        debug_info["steps"].append("JSON/dict 解析失败")
    
    # Step 4: 返回清理后的文本
    debug_info["steps"].append("返回清理后的文本答案")
    return answer_text.strip(), debug_info


def analyze_single_sample(sample: EvaluationSample, sample_id: int = 1):
    """详细分析单个样本的答案格式"""
    print("\n" + "="*80)
    print(f"样本 {sample_id} 详细分析")
    print("="*80)
    
    # 基本信息
    print(f"\n【基本信息】")
    print(f"实验ID: {sample.exp_id}")
    print(f"原始 Reward: {sample.reward}")
    print(f"原始判断: {'✓ 正确' if sample.reward >= 1.0 else '✗ 错误'}")
    
    # 问题
    print(f"\n【问题】")
    print(f"{sample.raw_question[:300]}...")
    
    # 标准答案分析
    print(f"\n【标准答案】")
    print(f"长度: {len(sample.correct_answer) if sample.correct_answer else 0}")
    
    if sample.correct_answer:
        # 尝试解析标准答案
        try:
            gt_parsed = json.loads(sample.correct_answer)
            print(f"格式: JSON ({type(gt_parsed).__name__})")
            print(f"内容预览: {json.dumps(gt_parsed, ensure_ascii=False)[:200]}...")
            if isinstance(gt_parsed, dict):
                print(f"JSON 键: {list(gt_parsed.keys())}")
        except:
            print(f"格式: 文本")
            print(f"内容: {sample.correct_answer[:200]}...")
    
    # 模型答案分析
    print(f"\n【模型答案】")
    print(f"长度: {len(sample.response) if sample.response else 0}")
    
    if sample.response:
        # 显示完整响应的关键部分
        print(f"\n原始响应（前500字符）:")
        print("-" * 80)
        print(sample.response[:500])
        print("-" * 80)
        
        # 调试版答案提取
        extracted, debug_info = extract_answer_debug(sample.response)
        
        print(f"\n答案提取过程:")
        for i, step in enumerate(debug_info["steps"], 1):
            print(f"  {i}. {step}")
        
        print(f"\n最终提取的答案:")
        print(f"长度: {len(extracted)}")
        print(f"内容: {extracted[:300]}...")
        
        # 尝试解析提取的答案
        extracted_parsed = _try_parse_dict_or_json(extracted)
        if extracted_parsed is not None:
            print(f"格式: JSON/dict ({type(extracted_parsed).__name__})")
            if isinstance(extracted_parsed, dict):
                print(f"JSON 键: {list(extracted_parsed.keys())}")
        else:
            print(f"格式: 文本")
    
    # 重新验证
    print(f"\n【重新验证】")
    try:
        result = verify_func(sample)
        new_reward = result["reward"]
        print(f"新 Reward: {new_reward}")
        print(f"新判断: {'✓ 正确' if new_reward >= 1.0 else '✗ 错误'}")
        
        if "reasoning" in result and result["reasoning"]:
            print(f"Reasoning: {result['reasoning'][:200]}...")
        
        # 判断是否匹配
        original_ok = sample.reward >= 1.0
        new_ok = new_reward >= 1.0
        
        if original_ok != new_ok:
            print(f"\n⚠️  判断不一致！")
            if new_ok and not original_ok:
                print(f"原本判断为错误，但重新验证为正确")
                print(f"→ 可能原因: 原始评估时的验证逻辑有问题")
            else:
                print(f"原本判断为正确，但重新验证为错误")
                print(f"→ 可能原因: 当前验证器更严格或答案格式有变化")
        else:
            print(f"\n✓ 判断一致")
            
    except Exception as e:
        print(f"验证失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 格式诊断
    print(f"\n【格式诊断】")
    
    issues = []
    
    # 检查 <answer> 标签
    if sample.response and "<answer>" not in sample.response.lower():
        issues.append("缺少 <answer> 标签")
    
    # 检查 \boxed{}
    if sample.response and "\\boxed{" not in sample.response:
        issues.append("缺少 \\boxed{} 格式")
    
    # 检查 JSON 格式
    if sample.response:
        if "<answer>" in sample.response.lower():
            answer_match = re.search(r'<answer>(.*?)</answer>', sample.response, re.DOTALL | re.IGNORECASE)
            if answer_match:
                answer_content = answer_match.group(1).strip()
                # 尝试从 boxed 中提取
                boxed_match = re.search(r'\\boxed\{(.*?)\}', answer_content, re.DOTALL)
                if boxed_match:
                    answer_content = boxed_match.group(1).strip()
                # 使用 _try_parse_dict_or_json 检查
                parsed = _try_parse_dict_or_json(answer_content)
                if parsed is None:
                    issues.append("JSON 格式错误")
    
    if issues:
        print("发现的问题:")
        for issue in issues:
            print(f"  ✗ {issue}")
    else:
        print("✓ 格式检查通过")


def compare_answer_formats(exp_id: str, limit: int = 5):
    """对比多个样本的答案格式"""
    print("\n" + "="*80)
    print(f"答案格式对比分析: {exp_id}")
    print("="*80)
    
    engine = SQLModelUtils.get_engine()
    
    with Session(engine) as session:
        # 获取错误的样本
        stmt = select(EvaluationSample).where(
            EvaluationSample.exp_id == exp_id
        ).where(
            EvaluationSample.reward < 1.0
        ).limit(limit)
        
        wrong_samples = list(session.exec(stmt).all())
        
        if not wrong_samples:
            print("未找到错误样本")
            return
        
        print(f"\n分析 {len(wrong_samples)} 个错误样本的答案格式\n")
        
        # 统计格式问题
        format_stats = {
            "missing_answer_tag": 0,
            "missing_boxed": 0,
            "json_parse_error": 0,
            "format_ok_but_wrong": 0,
            "total": len(wrong_samples)
        }
        
        for i, sample in enumerate(wrong_samples, 1):
            has_answer_tag = "<answer>" in (sample.response or "").lower()
            has_boxed = "\\boxed{" in (sample.response or "")
            
            # 尝试提取和解析
            can_parse_json = False
            if sample.response:
                try:
                    extracted, _ = extract_answer_debug(sample.response)
                    parsed = _try_parse_dict_or_json(extracted)
                    can_parse_json = (parsed is not None)
                except:
                    pass
            
            # 统计
            if not has_answer_tag:
                format_stats["missing_answer_tag"] += 1
            if not has_boxed:
                format_stats["missing_boxed"] += 1
            if not can_parse_json and sample.correct_answer:
                # 检查标准答案是否是 JSON
                gt_parsed = _try_parse_dict_or_json(sample.correct_answer)
                if gt_parsed is not None:
                    # 标准答案是 JSON，但模型答案不是
                    format_stats["json_parse_error"] += 1
            if has_answer_tag and has_boxed and can_parse_json:
                format_stats["format_ok_but_wrong"] += 1
            
            # 显示简要信息
            status = "✓" if (has_answer_tag and has_boxed) else "✗"
            print(f"{status} 样本 {i}: ", end="")
            if not has_answer_tag:
                print("缺<answer> ", end="")
            if not has_boxed:
                print("缺\\boxed{{}} ", end="")
            if not can_parse_json:
                print("JSON解析失败 ", end="")
            if has_answer_tag and has_boxed and can_parse_json:
                print("格式正常但答案错误", end="")
            print()
        
        # 打印统计
        print("\n" + "="*80)
        print("格式问题统计")
        print("="*80)
        print(f"总错误样本数: {format_stats['total']}")
        print(f"缺少 <answer> 标签: {format_stats['missing_answer_tag']} ({format_stats['missing_answer_tag']/format_stats['total']*100:.1f}%)")
        print(f"缺少 \\boxed{{}} 格式: {format_stats['missing_boxed']} ({format_stats['missing_boxed']/format_stats['total']*100:.1f}%)")
        print(f"JSON 解析失败: {format_stats['json_parse_error']} ({format_stats['json_parse_error']/format_stats['total']*100:.1f}%)")
        print(f"格式正常但答案错误: {format_stats['format_ok_but_wrong']} ({format_stats['format_ok_but_wrong']/format_stats['total']*100:.1f}%)")
        
        print("\n" + "="*80)
        print("诊断结论")
        print("="*80)
        
        format_issue_rate = (format_stats['missing_answer_tag'] + format_stats['missing_boxed'] + format_stats['json_parse_error']) / format_stats['total']
        
        if format_issue_rate > 0.5:
            print("🚨 严重的格式问题！")
            print(f"   {format_issue_rate*100:.1f}% 的错误是由于答案格式问题")
            print("   建议: 检查 agent 的 prompt，确保要求正确的答案格式")
        elif format_issue_rate > 0.2:
            print("⚠️  中等程度的格式问题")
            print(f"   {format_issue_rate*100:.1f}% 的错误是由于答案格式问题")
            print("   建议: 优化 agent 的答案格式指导")
        elif format_issue_rate > 0:
            print("✓ 轻微的格式问题")
            print(f"   只有 {format_issue_rate*100:.1f}% 的错误是由于格式问题")
            print(f"   {format_stats['format_ok_but_wrong']} 个样本格式正确但答案错误")
            print("   主要问题是推理错误，不是格式问题")
        else:
            print("✓ 无格式问题")
            print("   所有错误样本的格式都正确")
            print("   问题出在推理逻辑，不是答案格式")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="分析答案格式问题")
    parser.add_argument("--exp_id", type=str, default="zebralogic_practice_medium30_1", help="实验ID")
    parser.add_argument("--sample_id", type=int, help="分析特定样本（从1开始）")
    parser.add_argument("--limit", type=int, default=10, help="分析的样本数量")
    parser.add_argument("--detailed", action="store_true", help="显示详细分析")
    
    args = parser.parse_args()
    
    engine = SQLModelUtils.get_engine()
    
    # 如果指定了样本ID，详细分析该样本
    if args.sample_id:
        with Session(engine) as session:
            stmt = select(EvaluationSample).where(
                EvaluationSample.exp_id == args.exp_id
            ).limit(args.limit)
            
            samples = list(session.exec(stmt).all())
            
            if args.sample_id <= len(samples):
                analyze_single_sample(samples[args.sample_id - 1], args.sample_id)
            else:
                print(f"样本 {args.sample_id} 不存在（总共 {len(samples)} 个样本）")
    
    # 详细模式：逐个分析
    elif args.detailed:
        with Session(engine) as session:
            stmt = select(EvaluationSample).where(
                EvaluationSample.exp_id == args.exp_id
            ).where(
                EvaluationSample.reward < 1.0
            ).limit(args.limit)
            
            samples = list(session.exec(stmt).all())
            
            for i, sample in enumerate(samples, 1):
                analyze_single_sample(sample, i)
                if i < len(samples):
                    input("\n按 Enter 继续下一个样本...")
    
    # 默认：格式统计
    else:
        compare_answer_formats(args.exp_id, limit=args.limit)


if __name__ == "__main__":
    main()

