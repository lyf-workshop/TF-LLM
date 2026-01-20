#!/usr/bin/env python3
"""
分析 "Incomplete Reasoning" 检测的误报问题

这个脚本帮助您理解为什么几乎每个错误答案都会报告"Incomplete Reasoning"
"""

import json
import re
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.db import EvaluationSample
from utu.practice.verify.logic_with_error_analysis import verify_func


def analyze_verification_detection(response: str):
    """
    分析验证检测逻辑
    
    展示为什么检测会失败
    """
    print("\n" + "="*80)
    print("  验证检测逻辑分析")
    print("="*80)
    
    # V1 的检测逻辑
    verification_keywords = ["verify", "check", "confirm", "validate", "ensure"]
    has_verification = any(keyword in response.lower() for keyword in verification_keywords)
    
    print(f"\n【V1 检测逻辑】")
    print(f"  检查关键词: {verification_keywords}")
    print(f"  检测结果: {'✓ 通过' if has_verification else '✗ 失败'}")
    
    # 详细分析
    print(f"\n【详细分析】")
    found_keywords = []
    for keyword in verification_keywords:
        if keyword in response.lower():
            # 找到上下文
            idx = response.lower().find(keyword)
            context_start = max(0, idx - 30)
            context_end = min(len(response), idx + len(keyword) + 30)
            context = response[context_start:context_end]
            found_keywords.append((keyword, context))
    
    if found_keywords:
        print(f"  找到的关键词:")
        for keyword, context in found_keywords:
            print(f"    - '{keyword}': ...{context}...")
    else:
        print(f"  ✗ 没有找到任何验证关键词")
        
        # 检查是否有其他验证迹象
        print(f"\n  检查其他验证迹象:")
        
        # 检查中文验证词
        chinese_verification = ["验证", "检查", "确认", "确保", "核对"]
        found_chinese = [w for w in chinese_verification if w in response]
        if found_chinese:
            print(f"    ✓ 找到中文验证词: {found_chinese}")
            print(f"    ⚠️  但V1只检查英文关键词，所以会误报！")
        else:
            print(f"    ✗ 也没有找到中文验证词")
        
        # 检查验证性描述
        verification_patterns = [
            r'(?:all|所有).*(?:constraint|clue|线索|约束).*(?:satisfy|满足|符合)',
            r'(?:solution|答案|结果).*(?:correct|正确|符合)',
            r'(?:满足|符合).*(?:所有|全部).*(?:约束|条件|线索)',
        ]
        
        found_patterns = []
        for pattern in verification_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                found_patterns.append(pattern)
        
        if found_patterns:
            print(f"    ✓ 找到验证性描述模式: {len(found_patterns)} 个")
            print(f"    ⚠️  但V1不检查这些模式，所以会误报！")
        else:
            print(f"    ✗ 也没有找到验证性描述")
    
    return has_verification


def test_case_1_chinese_reasoning():
    """测试用例1: 中文推理（有验证但会被误报）"""
    print("\n" + "="*80)
    print("  测试用例 1: 中文推理（有验证行为，但会被误报）")
    print("="*80)
    
    ground_truth = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Peter", "Red"],
            ["2", "Alice", "Blue"],
            ["3", "Eric", "Green"]
        ]
    }
    
    wrong_answer = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Peter", "Blue"],
            ["2", "Alice", "Red"],
            ["3", "Eric", "Green"]
        ]
    }
    
    # 中文推理，有验证行为
    response = f"""
    让我系统地解决这个问题：
    
    1. 从线索1，Peter在第一个房子
    2. 从线索2，Alice在第二个房子
    3. 从线索3，Eric在第三个房子
    4. 让我检查所有约束是否都满足
    5. 是的，所有约束都满足
    
    <answer>
    {json.dumps(wrong_answer, ensure_ascii=False)}
    </answer>
    """
    
    print(f"\n【推理内容】")
    print(response[:300] + "...")
    
    # 分析验证检测
    has_verification = analyze_verification_detection(response)
    
    # 实际检测
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    result = verify_func(sample, enable_error_analysis=True)
    
    print(f"\n【V1 检测结果】")
    if result.get('reasoning'):
        if "Incomplete Reasoning" in result['reasoning']:
            print(f"  ✗ 报告了 'Incomplete Reasoning' (误报！)")
            print(f"\n  实际推理过程:")
            print(f"    - 有详细的步骤 (1-5)")
            print(f"    - 有验证行为 (步骤4-5)")
            print(f"    - 但因为没有英文关键词 'verify'，所以被误报")
        else:
            print(f"  ✓ 没有报告 'Incomplete Reasoning'")
    else:
        print(f"  (没有错误分析)")
    
    return result


def test_case_2_english_without_keyword():
    """测试用例2: 英文推理，有验证但没用关键词"""
    print("\n" + "="*80)
    print("  测试用例 2: 英文推理（有验证行为，但没用关键词）")
    print("="*80)
    
    ground_truth = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Peter", "Red"],
            ["2", "Alice", "Blue"]
        ]
    }
    
    wrong_answer = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Peter", "Blue"],
            ["2", "Alice", "Red"]
        ]
    }
    
    # 英文推理，有验证但没用关键词
    response = f"""
    Let me solve this systematically:
    
    1. From the first clue, Peter is in house 1
    2. From the second clue, Alice is in house 2
    3. Let me see if all constraints are satisfied
    4. Yes, all constraints are satisfied
    
    <answer>
    {json.dumps(wrong_answer, ensure_ascii=False)}
    </answer>
    """
    
    print(f"\n【推理内容】")
    print(response[:300] + "...")
    
    # 分析验证检测
    has_verification = analyze_verification_detection(response)
    
    # 实际检测
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    result = verify_func(sample, enable_error_analysis=True)
    
    print(f"\n【V1 检测结果】")
    if result.get('reasoning'):
        if "Incomplete Reasoning" in result['reasoning']:
            print(f"  ✗ 报告了 'Incomplete Reasoning' (误报！)")
            print(f"\n  实际推理过程:")
            print(f"    - 有详细的步骤 (1-4)")
            print(f"    - 有验证行为 (步骤3-4: 'all constraints are satisfied')")
            print(f"    - 但因为没有关键词 'verify/check/confirm'，所以被误报")
        else:
            print(f"  ✓ 没有报告 'Incomplete Reasoning'")
    else:
        print(f"  (没有错误分析)")
    
    return result


def test_case_3_with_keyword():
    """测试用例3: 使用关键词（应该通过）"""
    print("\n" + "="*80)
    print("  测试用例 3: 使用验证关键词（应该通过检测）")
    print("="*80)
    
    ground_truth = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Peter", "Red"],
            ["2", "Alice", "Blue"]
        ]
    }
    
    wrong_answer = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Peter", "Blue"],
            ["2", "Alice", "Red"]
        ]
    }
    
    # 使用验证关键词
    response = f"""
    Let me solve this:
    
    1. From clue 1, Peter is in house 1
    2. From clue 2, Alice is in house 2
    3. Let me verify all constraints are satisfied
    4. Yes, all constraints are satisfied
    
    <answer>
    {json.dumps(wrong_answer, ensure_ascii=False)}
    </answer>
    """
    
    print(f"\n【推理内容】")
    print(response[:300] + "...")
    
    # 分析验证检测
    has_verification = analyze_verification_detection(response)
    
    # 实际检测
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    result = verify_func(sample, enable_error_analysis=True)
    
    print(f"\n【V1 检测结果】")
    if result.get('reasoning'):
        if "Incomplete Reasoning" in result['reasoning']:
            print(f"  ✗ 仍然报告了 'Incomplete Reasoning'")
        else:
            print(f"  ✓ 没有报告 'Incomplete Reasoning' (正确)")
    else:
        print(f"  (没有错误分析)")
    
    return result


def summary():
    """总结"""
    print("\n" + "="*80)
    print("  问题总结")
    print("="*80)
    
    print("""
    V1 的 "Incomplete Reasoning" 检测问题：
    
    1. ❌ 检测方法过于简单
       - 只检查5个英文关键词: verify, check, confirm, validate, ensure
       - 不考虑实际验证行为
    
    2. ❌ 语言限制
       - 不支持中文推理
       - 即使有验证行为，用中文表达也会被误报
    
    3. ❌ 表达方式限制
       - 即使说"all constraints are satisfied"（所有约束都满足）
       - 如果没有用"verify"这个词，也会被误报
    
    4. ❌ 误报率高
       - 几乎每个错误答案都会报告
       - 因为大部分推理不会明确说"verify"
    
    解决方案：
    
    1. ✅ 使用 V2 版本 (logic_with_error_analysis_v2.py)
       - 更智能的检测
       - 避免误报
    
    2. ✅ 改进 V1 的检测逻辑
       - 检查验证行为，而不仅仅是关键词
       - 支持中文和多语言
       - 更宽松的判断标准
    
    3. ✅ 禁用这个检测
       - 如果误报太多，可以直接禁用
    """)


def main():
    """主函数"""
    print("\n" + "="*80)
    print("  'Incomplete Reasoning' 检测误报分析工具")
    print("="*80)
    print("\n这个工具帮助您理解为什么几乎每个错误答案都会报告")
    print("'Incomplete Reasoning'，以及如何解决这个问题。\n")
    
    try:
        test_case_1_chinese_reasoning()
        test_case_2_english_without_keyword()
        test_case_3_with_keyword()
        
        summary()
        
        print("\n" + "="*80)
        print("✅ 分析完成")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()






































































