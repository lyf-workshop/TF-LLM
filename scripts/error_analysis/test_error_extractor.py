"""
测试逻辑错误提取器的功能

展示如何从结构化推理过程中提取具体错误
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.db import EvaluationSample
from utu.practice.verify.logic_error_extractor import EnhancedLogicErrorAnalyzer, extract_errors_standalone


def test_contradiction_detection():
    """测试矛盾检测"""
    print("=" * 80)
    print("测试1: 矛盾检测")
    print("=" * 80)
    
    sample = EvaluationSample(
        raw_question="Who lives in house 1?",
        response="""
1. From clue 1, Peter is in house 1.
2. From clue 2, Alice is in house 2.
3. From clue 3, Peter is in house 3.
4. Therefore, Peter is in house 3.

<answer>
\\boxed{{"Peter is in house 3"}}
</answer>
""",
        ground_truth="Peter is in house 1",
        reward=0.0
    )
    
    analysis = extract_errors_standalone(sample)
    
    print(f"检测到错误: {analysis['has_errors']}")
    print(f"错误总结: {analysis['error_summary']}")
    print("\n详细错误:")
    for i, error in enumerate(analysis['errors'], 1):
        print(f"  {i}. {error}")
    print()


def test_constraint_violation():
    """测试约束违反检测"""
    print("=" * 80)
    print("测试2: 约束违反检测")
    print("=" * 80)
    
    sample = EvaluationSample(
        raw_question="What color is each house?",
        response="""
1. From clue 1, house 1 has color red.
2. From clue 2, house 2 has color blue.
3. From clue 3, house 3 has color red.
4. Therefore, house 1 and house 3 are both red.

<answer>
\\boxed{{"house 1: red, house 2: blue, house 3: red"}}
</answer>
""",
        ground_truth="house 1: red, house 2: blue, house 3: green",
        reward=0.0
    )
    
    analysis = extract_errors_standalone(sample)
    
    print(f"检测到错误: {analysis['has_errors']}")
    print(f"错误总结: {analysis['error_summary']}")
    print("\n详细错误:")
    for i, error in enumerate(analysis['errors'], 1):
        print(f"  {i}. {error}")
    print()


def test_reasoning_gap():
    """测试推理跳跃检测"""
    print("=" * 80)
    print("测试3: 推理跳跃检测")
    print("=" * 80)
    
    sample = EvaluationSample(
        raw_question="Who has a bird? Clue 1: Peter is in house 1. Clue 2: House 1 has a bird.",
        response="""
1. From clue 1, Peter is in house 1.
2. Peter has a bird.
3. Therefore, the answer is Peter.

<answer>
\\boxed{{"Peter"}}
</answer>
""",
        ground_truth="Peter",
        reward=0.0
    )
    
    analysis = extract_errors_standalone(sample)
    
    print(f"检测到错误: {analysis['has_errors']}")
    print(f"错误总结: {analysis['error_summary']}")
    print("\n详细错误:")
    for i, error in enumerate(analysis['errors'], 1):
        print(f"  {i}. {error}")
    print()


def test_unused_clues():
    """测试未使用线索检测"""
    print("=" * 80)
    print("测试4: 未使用线索检测")
    print("=" * 80)
    
    sample = EvaluationSample(
        raw_question="""
Clue 1: Peter is in house 1.
Clue 2: Alice is in house 2.
Clue 3: The person in house 1 has a bird.
Clue 4: The person in house 2 has a cat.
""",
        response="""
1. From clue 1, Peter is in house 1.
2. From clue 2, Alice is in house 2.
3. Therefore, Peter and Alice are in different houses.

<answer>
\\boxed{{"Peter: house 1, Alice: house 2"}}
</answer>
""",
        ground_truth="Peter: house 1, Alice: house 2",
        reward=0.0
    )
    
    analysis = extract_errors_standalone(sample)
    
    print(f"检测到错误: {analysis['has_errors']}")
    print(f"错误总结: {analysis['error_summary']}")
    print("\n详细错误:")
    for i, error in enumerate(analysis['errors'], 1):
        print(f"  {i}. {error}")
    print()


def test_good_reasoning():
    """测试正确的推理（应该不检测到错误）"""
    print("=" * 80)
    print("测试5: 正确的推理格式")
    print("=" * 80)
    
    sample = EvaluationSample(
        raw_question="""
Clue 1: Peter is in house 1.
Clue 2: The person in house 1 has a bird.
""",
        response="""
1. From clue 1, Peter is in house 1.
2. From clue 2, the person in house 1 has a bird.
3. Therefore, Peter has a bird (combining clues 1 and 2).

Verification:
- Clue 1: Peter is in house 1. ✓
- Clue 2: Person in house 1 has a bird. ✓
- All constraints satisfied.

<answer>
\\boxed{{"Peter has a bird"}}
</answer>
""",
        ground_truth="Peter has a bird",
        reward=0.0
    )
    
    analysis = extract_errors_standalone(sample)
    
    print(f"检测到错误: {analysis['has_errors']}")
    print(f"错误总结: {analysis['error_summary']}")
    print("\n详细错误:")
    if analysis['errors']:
        for i, error in enumerate(analysis['errors'], 1):
            print(f"  {i}. {error}")
    else:
        print("  (无错误)")
    print()


if __name__ == "__main__":
    print("\n逻辑错误提取器功能测试\n")
    
    test_contradiction_detection()
    test_constraint_violation()
    test_reasoning_gap()
    test_unused_clues()
    test_good_reasoning()
    
    print("=" * 80)
    print("测试完成！")
    print("=" * 80)

