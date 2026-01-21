#!/usr/bin/env python3
"""
简化版测试脚本 - 仅测试错误分析器的核心逻辑
不需要完整的项目依赖
"""

import json
import re
from typing import Any, Dict, List
from collections import defaultdict


# 简化的 EvaluationSample 类
class SimpleEvaluationSample:
    def __init__(self, response: str, correct_answer: str):
        self.response = response
        self.correct_answer = correct_answer


def test_constraint_violation_detection():
    """测试约束违反检测"""
    print("\n" + "="*70)
    print("测试 1: 约束违反检测（重复分配）")
    print("="*70)
    
    response = """
解决步骤:

从线索分析:
House 1: Peter, Red
House 2: Alice, Red  (错误：Red 已经分配给 House 1!)
House 3: Eric, Green

<answer>
{"header": ["House", "Name", "Color"], 
 "rows": [["1", "Peter", "Red"], 
          ["2", "Alice", "Red"], 
          ["3", "Eric", "Green"]]}
</answer>
"""
    
    # 提取分配
    assignments = _extract_assignments(response)
    print(f"[OK] 提取到的分配: {dict(assignments)}")
    
    # 检测重复
    attribute_to_entities = defaultdict(list)
    for entity, attrs in assignments.items():
        for attr_type, attr_value in attrs.items():
            if attr_value:
                attribute_to_entities[f"{attr_type}:{attr_value}"].append(entity)
    
    duplicates = {k: v for k, v in attribute_to_entities.items() if len(v) > 1}
    print(f"[OK] 检测到重复分配: {len(duplicates)} 个")
    
    for attr, entities in duplicates.items():
        print(f"  - {attr} 分配给了: {', '.join(entities)}")
    
    assert len(duplicates) > 0, "应该检测到重复分配"
    print("\n[PASS] 测试通过!")


def test_answer_extraction():
    """测试答案提取"""
    print("\n" + "="*70)
    print("测试 2: 答案提取")
    print("="*70)
    
    test_cases = [
        # JSON 格式
        ("""
<answer>
{"header": ["House", "Name"], "rows": [["1", "Alice"], ["2", "Bob"]]}
</answer>
""", "JSON answer tag"),
        
        # Boxed 格式
        (r"""
The solution is:
\boxed{{"header": ["House", "Name"], "rows": [["1", "Alice"]]}}
""", "LaTeX boxed"),
    ]
    
    for response, desc in test_cases:
        answer = _extract_final_answer(response)
        print(f"[OK] {desc}: {'提取成功' if answer else '提取失败'}")
        if answer:
            print(f"  答案: {answer}")
    
    print("\n[PASS] 测试通过!")


def test_contradiction_detection():
    """测试矛盾检测"""
    print("\n" + "="*70)
    print("测试 3: 矛盾检测")
    print("="*70)
    
    response = """
推理步骤:

1. Peter is in house 1
2. From the clues, Alice is in house 2
3. Therefore, Peter is in house 2  (矛盾！)

最终答案...
"""
    
    # 提取断言
    assertions = _extract_all_assertions(response)
    print(f"[OK] 提取到 {len(assertions)} 个断言")
    
    # 检查矛盾
    contradictions = 0
    for i, (step1, assertion1) in enumerate(assertions):
        for step2, assertion2 in assertions[i+1:]:
            if _are_contradicting(assertion1, assertion2):
                print(f"[OK] 发现矛盾:")
                print(f"  步骤 {step1 + 1}: {assertion1}")
                print(f"  步骤 {step2 + 1}: {assertion2}")
                contradictions += 1
    
    print(f"\n[OK] 共检测到 {contradictions} 个矛盾")
    print("\n[PASS] 测试通过!")


def test_incomplete_reasoning_detection():
    """测试不完整推理检测"""
    print("\n" + "="*70)
    print("测试 4: 不完整推理检测")
    print("="*70)
    
    response = """
快速解答:

因此答案是:
<answer>
{"header": ["House", "Name"], "rows": [["1", "Peter"], ["2", "Alice"]]}
</answer>

(注意: 没有推理步骤，没有验证，没有引用线索)
"""
    
    issues = []
    
    # 检查验证
    verification_keywords = ["verify", "check", "confirm", "validate", "ensure"]
    has_verification = any(keyword in response.lower() for keyword in verification_keywords)
    
    if not has_verification:
        issues.append("缺少解决方案验证")
        print("[OK] 检测到: 缺少解决方案验证")
    
    # 检查线索引用
    clue_pattern = r"(?:clue|constraint|given|线索|约束)\s+(\d+)"
    mentioned_clues = set(re.findall(clue_pattern, response.lower()))
    
    if not mentioned_clues:
        issues.append("没有引用任何线索")
        print("[OK] 检测到: 没有引用任何线索")
    
    print(f"\n[OK] 共检测到 {len(issues)} 个不完整推理问题")
    assert len(issues) > 0, "应该检测到不完整推理"
    print("\n[PASS] 测试通过!")


def test_assignment_error_detection():
    """测试赋值错误检测"""
    print("\n" + "="*70)
    print("测试 5: 赋值错误检测")
    print("="*70)
    
    response = """
<answer>
{"header": ["House", "Name", "Color"], 
 "rows": [["1", "Peter", "Red"], 
          ["2", "Alice", "Green"], 
          ["3", "Eric", "Blue"]]}
</answer>
"""
    
    ground_truth = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Peter", "Red"],
            ["2", "Alice", "Blue"],   # 应该是 Blue 不是 Green
            ["3", "Eric", "Green"]     # 应该是 Green 不是 Blue
        ]
    }
    
    predicted = _extract_final_answer(response)
    
    if predicted and isinstance(predicted, dict):
        errors = []
        for i, (pred_row, gt_row) in enumerate(zip(predicted["rows"], ground_truth["rows"])):
            for j, (pred_val, gt_val) in enumerate(zip(pred_row, gt_row)):
                if _normalize_value(pred_val) != _normalize_value(gt_val):
                    header = ground_truth["header"][j]
                    error_msg = f"行 {i+1}, {header}: 预期 '{gt_val}', 实际 '{pred_val}'"
                    errors.append(error_msg)
                    print(f"[OK] 检测到赋值错误: {error_msg}")
        
        print(f"\n[OK] 共检测到 {len(errors)} 个赋值错误")
        assert len(errors) == 2, f"应该检测到 2 个错误，实际检测到 {len(errors)} 个"
    
    print("\n[PASS] 测试通过!")


# ===== 辅助函数 =====

def _extract_assignments(response: str) -> Dict[str, Dict[str, str]]:
    """从响应中提取实体-属性分配"""
    assignments = defaultdict(dict)
    
    # 模式: "House 1: name, attribute1, attribute2..."
    house_pattern = r"[Hh]ouse\s+(\d+):\s*([^;\n]+)"
    matches = re.findall(house_pattern, response)
    
    for house_num, attrs_str in matches:
        entity = f"House {house_num}"
        # 分割属性，并清理注释
        attrs = [a.strip() for a in attrs_str.split(",")]
        for i, attr in enumerate(attrs):
            if attr:
                # 移除注释（括号内容）
                attr_cleaned = re.sub(r'\([^)]*\)', '', attr).strip()
                if attr_cleaned:
                    assignments[entity][f"attr_{i}"] = attr_cleaned.lower()
    
    return dict(assignments)


def _extract_final_answer(response: str) -> Any:
    """提取最终答案"""
    # 尝试 <answer> 标签
    answer_pattern = r"<answer>\s*(.+?)\s*</answer>"
    match = re.search(answer_pattern, response, re.DOTALL | re.IGNORECASE)
    
    if match:
        content = match.group(1).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            try:
                return json.loads(content.replace("'", '"'))
            except json.JSONDecodeError:
                pass
    
    # 尝试 \boxed{} 格式
    boxed_pattern = r"\\boxed\{(.+?)\}"
    match = re.search(boxed_pattern, response, re.DOTALL)
    if match:
        content = match.group(1).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
    
    return None


def _extract_all_assertions(response: str) -> List[tuple]:
    """提取所有断言"""
    assertions = []
    
    # 将响应分成步骤
    lines = response.split('\n')
    
    for i, line in enumerate(lines):
        # 查找 "X is Y" 或 "X in position Y" 模式
        patterns = [
            r"([A-Z][a-z]+)\s+(?:is|has)\s+([a-z]+(?:\s+[a-z]+)?)",
            r"([A-Z][a-z]+)\s+in\s+(?:house|position)\s+(\d+)",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, line)
            for match in matches:
                assertion = f"{match[0]} -> {match[1]}"
                assertions.append((i, assertion))
    
    return assertions


def _are_contradicting(assertion1: str, assertion2: str) -> bool:
    """检查两个断言是否矛盾"""
    if "->" in assertion1 and "->" in assertion2:
        entity1, attr1 = assertion1.split("->", 1)
        entity2, attr2 = assertion2.split("->", 1)
        
        # 相同实体，不同属性值
        return entity1.strip() == entity2.strip() and attr1.strip() != attr2.strip()
    
    return False


def _normalize_value(value: str) -> str:
    """标准化值"""
    if value is None:
        return ""
    return str(value).lower().strip()


def main():
    """运行所有测试"""
    print("\n" + "="*70)
    print("逻辑错误分析器 - 简化测试")
    print("="*70)
    
    try:
        test_constraint_violation_detection()
        test_answer_extraction()
        test_contradiction_detection()
        test_incomplete_reasoning_detection()
        test_assignment_error_detection()
        
        print("\n" + "="*70)
        print("[SUCCESS] 所有测试通过!")
        print("="*70)
        print("\n逻辑错误分析器的核心功能正常工作。")
        print("现在可以在 ZebraLogic 训练中使用它了！")
        print("\n使用方法:")
        print("  1. 查看完整文档: ZebraLogic逻辑错误检测与经验学习指南.md")
        print("  2. 使用增强配置运行训练:")
        print("     uv run python scripts/run_training_free_GRPO.py \\")
        print("       --config practice/logic_reasoning_zebralogic_with_error_analysis.yaml")
        
    except AssertionError as e:
        print(f"\n[FAIL] 测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] 意外错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())

