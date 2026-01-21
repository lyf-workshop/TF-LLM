#!/usr/bin/env python3
"""
诊断脚本：查看增强验证器返回的错误信息

这个脚本帮助您了解增强验证器实际返回了什么错误信息，
以及为什么可能影响训练效果。
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.db import EvaluationSample
from utu.practice.verify.logic import verify_func as basic_verify_func
from utu.practice.verify.logic_with_error_analysis import verify_func as enhanced_verify_func


def print_section(title: str, width: int = 80):
    """打印分节标题"""
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width + "\n")


def print_result(label: str, result: dict, show_full_reasoning: bool = True):
    """打印验证结果"""
    print(f"\n【{label}】")
    print(f"  Reward: {result.get('reward', 'N/A')}")
    print(f"  Reasoning: {result.get('reasoning', 'None')}")
    
    if show_full_reasoning and result.get('reasoning'):
        print(f"\n  完整 Reasoning 内容:")
        print("  " + "-" * 76)
        for line in result['reasoning'].split('\n'):
            print(f"  {line}")
        print("  " + "-" * 76)
    
    if result.get('detailed_errors'):
        print(f"\n  详细错误信息 (detailed_errors):")
        print("  " + "-" * 76)
        print(f"  {json.dumps(result['detailed_errors'], indent=4, ensure_ascii=False)}")
        print("  " + "-" * 76)
    
    if result.get('total_errors'):
        print(f"  总错误数: {result.get('total_errors')}")


def test_case_1_constraint_violation():
    """测试用例1: 约束违反（重复分配）"""
    print_section("测试用例 1: 约束违反 - 重复分配颜色")
    
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
            ["1", "Peter", "Red"],
            ["2", "Alice", "Red"],  # 重复颜色
            ["3", "Eric", "Green"]
        ]
    }
    
    response = """
    让我逐步解决这个问题：
    
    1. 从线索中，我确定：
       - House 1: Peter, Red
       - House 2: Alice, Red  (注意：这里重复了红色！)
       - House 3: Eric, Green
    
    <answer>
    """ + json.dumps(wrong_answer, ensure_ascii=False) + """
    </answer>
    """
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    # 基本验证器
    basic_result = basic_verify_func(sample)
    print_result("基本验证器", basic_result, show_full_reasoning=False)
    
    # 增强验证器 - 标准模式
    enhanced_result = enhanced_verify_func(sample, enable_error_analysis=True)
    print_result("增强验证器 (标准)", enhanced_result, show_full_reasoning=True)
    
    # 增强验证器 - 详细模式
    enhanced_detailed = enhanced_verify_func(
        sample,
        enable_error_analysis=True,
        detailed_errors=True
    )
    print_result("增强验证器 (详细模式)", enhanced_detailed, show_full_reasoning=True)


def test_case_2_contradiction():
    """测试用例2: 逻辑矛盾"""
    print_section("测试用例 2: 逻辑矛盾")
    
    ground_truth = {
        "header": ["House", "Name"],
        "rows": [
            ["1", "Peter"],
            ["2", "Alice"]
        ]
    }
    
    wrong_answer = {
        "header": ["House", "Name"],
        "rows": [
            ["1", "Alice"],
            ["2", "Peter"]
        ]
    }
    
    response = """
    推理过程：
    
    1. Peter 在 house 1。
    2. 从线索3，Alice 在 house 2。
    3. 因此，Peter 在 house 2。  (矛盾！与步骤1冲突)
    
    <answer>
    """ + json.dumps(wrong_answer, ensure_ascii=False) + """
    </answer>
    """
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    enhanced_result = enhanced_verify_func(sample, enable_error_analysis=True, detailed_errors=True)
    print_result("增强验证器", enhanced_result, show_full_reasoning=True)


def test_case_3_incomplete_reasoning():
    """测试用例3: 推理不完整"""
    print_section("测试用例 3: 推理不完整")
    
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
    
    response = """
    快速解答：
    
    因此，答案是：
    <answer>
    """ + json.dumps(wrong_answer, ensure_ascii=False) + """
    </answer>
    
    (注意：没有显示推理步骤，没有验证，没有引用线索)
    """
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    enhanced_result = enhanced_verify_func(sample, enable_error_analysis=True, detailed_errors=True)
    print_result("增强验证器", enhanced_result, show_full_reasoning=True)


def test_case_4_assignment_errors():
    """测试用例4: 赋值错误"""
    print_section("测试用例 4: 赋值错误")
    
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
            ["1", "Peter", "Red"],
            ["2", "Alice", "Green"],  # 应该是 Blue
            ["3", "Eric", "Blue"]     # 应该是 Green
        ]
    }
    
    response = """
    经过仔细分析：
    
    1. Peter 在 house 1，颜色是红色
    2. Alice 在 house 2，颜色是绿色  (应该是蓝色！)
    3. Eric 在 house 3，颜色是蓝色   (应该是绿色！)
    
    <answer>
    """ + json.dumps(wrong_answer, ensure_ascii=False) + """
    </answer>
    """
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    enhanced_result = enhanced_verify_func(sample, enable_error_analysis=True, detailed_errors=True)
    print_result("增强验证器", enhanced_result, show_full_reasoning=True)


def test_case_5_correct_answer():
    """测试用例5: 正确答案（不应该有错误分析）"""
    print_section("测试用例 5: 正确答案")
    
    ground_truth = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Peter", "Red"],
            ["2", "Alice", "Blue"],
            ["3", "Eric", "Green"]
        ]
    }
    
    response = """
    完美推理：
    
    1. 仔细分析了所有线索
    2. 验证了每个约束
    3. 解决方案是正确的
    
    <answer>
    """ + json.dumps(ground_truth, ensure_ascii=False) + """
    </answer>
    """
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    basic_result = basic_verify_func(sample)
    enhanced_result = enhanced_verify_func(sample, enable_error_analysis=True)
    
    print_result("基本验证器", basic_result, show_full_reasoning=False)
    print_result("增强验证器", enhanced_result, show_full_reasoning=False)
    
    print("\n  ✓ 正确答案不应该触发错误分析")


def test_case_6_error_analysis_disabled():
    """测试用例6: 错误分析被禁用"""
    print_section("测试用例 6: 错误分析禁用 vs 启用")
    
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
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=f"<answer>{json.dumps(wrong_answer)}</answer>",
        correct_answer=json.dumps(ground_truth)
    )
    
    result_disabled = enhanced_verify_func(sample, enable_error_analysis=False)
    result_enabled = enhanced_verify_func(sample, enable_error_analysis=True)
    
    print_result("错误分析禁用", result_disabled, show_full_reasoning=False)
    print_result("错误分析启用", result_enabled, show_full_reasoning=True)


def analyze_potential_issues():
    """分析可能的问题"""
    print_section("⚠️  可能影响训练效果的问题分析")
    
    issues = [
        {
            "问题": "错误信息可能过于详细",
            "描述": "如果错误分析返回的信息太长或太复杂，可能会干扰经验生成",
            "建议": "检查 reasoning 字段的长度和复杂度"
        },
        {
            "问题": "错误分析可能不准确",
            "描述": "LogicErrorAnalyzer 可能误判或漏判错误",
            "建议": "对比 detailed_errors 和实际错误，检查分析准确性"
        },
        {
            "问题": "错误信息格式可能不适合LLM",
            "描述": "格式化的错误信息可能不符合经验生成器的期望格式",
            "建议": "检查 reasoning 字段的格式是否与经验生成器兼容"
        },
        {
            "问题": "错误分析可能产生噪音",
            "描述": "即使答案正确，错误分析也可能产生误报",
            "建议": "确保正确答案不触发错误分析（已实现）"
        },
        {
            "问题": "错误分析可能太慢",
            "描述": "错误分析可能增加验证时间，影响训练速度",
            "建议": "如果不需要详细错误，可以禁用错误分析"
        }
    ]
    
    for i, issue in enumerate(issues, 1):
        print(f"\n{i}. {issue['问题']}")
        print(f"   描述: {issue['描述']}")
        print(f"   建议: {issue['建议']}")


def compare_output_formats():
    """对比输出格式"""
    print_section("📊 输出格式对比")
    
    print("""
    基本验证器返回格式:
    {
        "reward": 0.0 or 1.0,
        "reasoning": None or "错误信息"
    }
    
    增强验证器返回格式 (标准模式):
    {
        "reward": 0.0 or 1.0,
        "reasoning": "格式化的错误分析字符串" or None
    }
    
    增强验证器返回格式 (详细模式):
    {
        "reward": 0.0 or 1.0,
        "reasoning": "格式化的错误分析字符串" or None,
        "detailed_errors": {
            "constraint_violations": [...],
            "contradictions": [...],
            "assignment_errors": [...],
            "incomplete_reasoning": [...],
            "logical_inconsistencies": [...]
        },
        "total_errors": 5
    }
    
    ⚠️  注意: reasoning 字段的内容会被传递给经验生成器！
    如果格式不合适，可能会影响训练效果。
    """)


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("  增强验证器错误信息诊断工具")
    print("=" * 80)
    print("\n这个工具帮助您了解增强验证器返回的错误信息格式和内容。")
    print("如果您发现使用增强验证器后训练效果变差，这个工具可以帮助诊断问题。\n")
    
    try:
        # 运行各种测试用例
        test_case_1_constraint_violation()
        test_case_2_contradiction()
        test_case_3_incomplete_reasoning()
        test_case_4_assignment_errors()
        test_case_5_correct_answer()
        test_case_6_error_analysis_disabled()
        
        # 分析可能的问题
        analyze_potential_issues()
        
        # 对比输出格式
        compare_output_formats()
        
        print_section("💡 建议")
        print("""
        1. 检查 reasoning 字段的实际内容，看是否过长或格式不合适
        2. 对比使用基本验证器和增强验证器的训练结果
        3. 如果错误分析不准确，考虑禁用或改进 LogicErrorAnalyzer
        4. 如果错误信息格式不合适，可以修改 _format_error_reasoning 函数
        5. 考虑使用 enable_error_analysis=False 来禁用错误分析，只使用基本验证
        
        如果问题仍然存在，可以：
        - 查看实际训练中的 reasoning 字段内容
        - 检查经验生成器如何处理这些错误信息
        - 考虑简化错误信息的格式
        """)
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()







































































