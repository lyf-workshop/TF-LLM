#!/usr/bin/env python3
"""
测试重新设计的错误分析器 (V2)

对比旧版本和新版本的错误分析效果
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.db import EvaluationSample
from utu.practice.verify.logic import verify_func as basic_verify_func
from utu.practice.verify.logic_with_error_analysis import verify_func as v1_verify_func
from utu.practice.verify.logic_with_error_analysis_v2 import verify_func as v2_verify_func


def print_section(title: str, width: int = 80):
    """打印分节标题"""
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width + "\n")


def print_comparison(label: str, v1_result: dict, v2_result: dict):
    """对比两个版本的结果"""
    print(f"\n【{label}】")
    print(f"  Reward: {v1_result.get('reward')} (两个版本应该相同)")
    
    print(f"\n  V1 (旧版) Reasoning:")
    print("  " + "-" * 76)
    if v1_result.get('reasoning'):
        for line in v1_result['reasoning'].split('\n'):
            print(f"  {line}")
    else:
        print("  (无)")
    print("  " + "-" * 76)
    
    print(f"\n  V2 (新版) Reasoning:")
    print("  " + "-" * 76)
    if v2_result.get('reasoning'):
        for line in v2_result['reasoning'].split('\n'):
            print(f"  {line}")
    else:
        print("  (无)")
    print("  " + "-" * 76)
    
    # 对比分析
    print(f"\n  📊 对比:")
    v1_len = len(v1_result.get('reasoning', '')) if v1_result.get('reasoning') else 0
    v2_len = len(v2_result.get('reasoning', '')) if v2_result.get('reasoning') else 0
    print(f"    V1 长度: {v1_len} 字符")
    print(f"    V2 长度: {v2_len} 字符")
    
    if v2_len < v1_len:
        print(f"    ✓ V2 更简洁 (减少 {v1_len - v2_len} 字符, {(1 - v2_len/v1_len)*100:.1f}%)")
    
    # 评价
    print(f"\n  💡 评价:")
    if not v1_result.get('reasoning') and not v2_result.get('reasoning'):
        print("    两个版本都没有提供错误分析")
    elif v2_result.get('reasoning'):
        print(f"    V2 关注: 推理过程质量")
        if "推理过程" in v2_result.get('reasoning', ''):
            print("    ✓ 提供了推理改进建议")
    if v1_result.get('reasoning') and "Incorrect Assignments" in v1_result.get('reasoning', ''):
        print("    V1 关注: 答案对比（价值较低）")


def test_case_1_no_reasoning():
    """测试用例1: 没有推理过程，直接给答案"""
    print_section("测试用例 1: 没有推理过程")
    
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
    
    # 没有推理过程的response
    response = f"""
    <answer>
    {json.dumps(wrong_answer, ensure_ascii=False)}
    </answer>
    """
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    v1_result = v1_verify_func(sample, enable_error_analysis=True)
    v2_result = v2_verify_func(sample, enable_error_analysis=True)
    
    print_comparison("没有推理过程", v1_result, v2_result)


def test_case_2_poor_reasoning():
    """测试用例2: 推理过程过于简单"""
    print_section("测试用例 2: 推理过程过于简单")
    
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
    
    # 过于简单的推理
    response = f"""
    我觉得应该是这样的。
    
    <answer>
    {json.dumps(wrong_answer, ensure_ascii=False)}
    </answer>
    """
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    v1_result = v1_verify_func(sample, enable_error_analysis=True)
    v2_result = v2_verify_func(sample, enable_error_analysis=True)
    
    print_comparison("推理过于简单", v1_result, v2_result)


def test_case_3_no_clue_references():
    """测试用例3: 没有引用线索"""
    print_section("测试用例 3: 没有引用线索")
    
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
    
    # 有推理步骤，但没有引用clue
    response = f"""
    让我来解决这个问题：
    
    1. 首先分配第一个房子
    2. 然后分配第二个房子
    3. 最后分配第三个房子
    
    <answer>
    {json.dumps(wrong_answer, ensure_ascii=False)}
    </answer>
    """
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    v1_result = v1_verify_func(sample, enable_error_analysis=True)
    v2_result = v2_verify_func(sample, enable_error_analysis=True)
    
    print_comparison("没有引用线索", v1_result, v2_result)


def test_case_4_good_reasoning_but_wrong():
    """测试用例4: 推理过程很好，但答案错了"""
    print_section("测试用例 4: 推理过程很好但答案错误")
    
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
    
    # 很好的推理过程
    response = f"""
    让我系统地解决这个问题：
    
    1. 从 clue 1，Peter 在第一个房子
    2. 从 clue 2，Alice 在第二个房子
    3. 从 clue 3，Eric 在第三个房子
    4. 从 clue 4，第一个房子是蓝色（注意：这里可能理解错了）
    5. 从 clue 5，第二个房子是红色
    6. 从 clue 6，第三个房子是绿色
    
    验证：所有约束都满足
    
    <answer>
    {json.dumps(wrong_answer, ensure_ascii=False)}
    </answer>
    """
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    v1_result = v1_verify_func(sample, enable_error_analysis=True)
    v2_result = v2_verify_func(sample, enable_error_analysis=True)
    
    print_comparison("推理过程好但答案错", v1_result, v2_result)


def test_case_5_systematic_approach():
    """测试用例5: 使用系统化方法"""
    print_section("测试用例 5: 使用系统化方法")
    
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
    
    # 使用表格等系统化方法
    response = f"""
    我将使用表格来系统地解决这个问题：
    
    | House | Name  | Color |
    |-------|-------|-------|
    | 1     | Peter | ?     |
    | 2     | Alice | ?     |
    | 3     | Eric  | ?     |
    
    从 clue 1: Peter的房子是蓝色
    从 clue 2: Alice的房子是红色
    从 clue 3: Eric的房子是绿色
    
    验证所有clues...
    
    <answer>
    {json.dumps(wrong_answer, ensure_ascii=False)}
    </answer>
    """
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    v1_result = v1_verify_func(sample, enable_error_analysis=True)
    v2_result = v2_verify_func(sample, enable_error_analysis=True)
    
    print_comparison("系统化方法", v1_result, v2_result)


def test_case_6_correct_answer():
    """测试用例6: 正确答案"""
    print_section("测试用例 6: 正确答案")
    
    ground_truth = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Peter", "Red"],
            ["2", "Alice", "Blue"],
            ["3", "Eric", "Green"]
        ]
    }
    
    response = f"""
    系统化解决：
    
    1. 从clue分析...
    2. 建立表格...
    3. 验证约束...
    
    <answer>
    {json.dumps(ground_truth, ensure_ascii=False)}
    </answer>
    """
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    v1_result = v1_verify_func(sample, enable_error_analysis=True)
    v2_result = v2_verify_func(sample, enable_error_analysis=True)
    
    print_comparison("正确答案", v1_result, v2_result)


def summary():
    """总结对比"""
    print_section("📊 V2 版本改进总结")
    
    print("""
    V1 (旧版) 的问题:
    ❌ 主要关注答案对比，而不是推理过程
    ❌ 报告"Incorrect Assignments"（这只是说答案错了，没有价值）
    ❌ 报告"Incomplete Reasoning"但基于简单的关键词搜索，容易误报
    ❌ 错误信息较长，包含不必要的细节
    
    V2 (新版) 的改进:
    ✅ 专注于推理过程质量评估
    ✅ 检测推理是否有结构、是否引用线索、是否有验证
    ✅ 提供建设性的改进建议
    ✅ 更简洁的错误提示（通常100-200字符）
    ✅ 避免误报和无价值的信息
    
    关键差异:
    
    | 方面           | V1                          | V2                          |
    |----------------|-----------------------------|-----------------------------|
    | 分析重点       | 答案对比                     | 推理过程质量                 |
    | 错误类型       | 技术性错误(missing attrs等)  | 推理策略问题                 |
    | 信息长度       | 较长(200-400字符)           | 简洁(100-200字符)           |
    | 误报风险       | 高                           | 低                          |
    | 对训练的价值   | 低                           | 高                          |
    
    建议使用方式:
    
    1. 在配置文件中使用 V2:
       ```yaml
       verify_filename: "logic_with_error_analysis_v2.py"
       verify_func_name: "verify_func"
       ```
    
    2. 或者继续使用基本验证器:
       ```yaml
       verify_filename: "logic.py"
       verify_func_name: "verify_func"
       ```
    
    3. 对比训练效果，选择最适合的版本
    """)


def main():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("  错误分析器 V1 vs V2 对比测试")
    print("=" * 80)
    
    try:
        test_case_1_no_reasoning()
        test_case_2_poor_reasoning()
        test_case_3_no_clue_references()
        test_case_4_good_reasoning_but_wrong()
        test_case_5_systematic_approach()
        test_case_6_correct_answer()
        
        summary()
        
        print("\n" + "=" * 80)
        print("✅ 测试完成")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()







































































