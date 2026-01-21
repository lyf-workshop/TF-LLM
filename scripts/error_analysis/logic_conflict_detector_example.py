"""
逻辑冲突检测器使用示例

演示如何使用 logic_conflict_detector 检测逻辑冲突并生成经验总结
"""

import asyncio
import json
import sys
from pathlib import Path

# 添加scripts目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from utu.db import EvaluationSample
from utu.utils import SimplifiedAsyncOpenAI, get_logger
from logic_conflict_detector import LogicConflictDetector

logger = get_logger(__name__)


async def example_single_sample():
    """示例1: 分析单个样本"""
    print("=" * 70)
    print("示例1: 分析单个样本")
    print("=" * 70)
    
    # 创建一个示例样本（包含逻辑矛盾的推理）
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        raw_question="""
        Solve this logic puzzle:
        Clue 1: Peter is in house 1
        Clue 2: Alice is in house 2
        Clue 3: The person in house 1 has a bird
        """,
        response="""
        Let me solve this step by step:
        
        1. From clue 1, Peter is in house 1
        2. From clue 3, the person in house 1 has a bird
        3. Therefore, Peter has a bird
        4. But wait, from clue 2, Alice is in house 2
        5. Actually, Peter is in house 2 (CONTRADICTION with step 1!)
        
        <answer>
        {"header": ["House", "Name"], "rows": [["1", "Alice"], ["2", "Peter"]]}
        </answer>
        """,
        correct_answer=json.dumps({
            "header": ["House", "Name"],
            "rows": [["1", "Peter"], ["2", "Alice"]]
        })
    )
    
    # 初始化检测器（不使用LLM，只检测冲突）
    detector = LogicConflictDetector(llm=None)
    
    # 检测冲突
    conflict_analysis = detector.detect_conflicts(sample)
    
    print(f"\n冲突检测结果:")
    print(f"  是否有冲突: {conflict_analysis['has_conflicts']}")
    print(f"  冲突总数: {conflict_analysis['total_conflicts']}")
    print(f"  摘要: {conflict_analysis['summary']}")
    
    print(f"\n详细冲突:")
    for conflict_type, conflict_list in conflict_analysis['conflicts_by_type'].items():
        if conflict_list:
            print(f"\n  {conflict_type}:")
            for conflict in conflict_list:
                print(f"    - {conflict.get('description', str(conflict))}")


async def example_with_experience_generation():
    """示例2: 检测冲突并生成经验总结"""
    print("\n" + "=" * 70)
    print("示例2: 检测冲突并生成经验总结")
    print("=" * 70)
    
    # 注意：这个示例需要配置LLM
    # 如果未配置，会跳过经验生成
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        raw_question="""
        Logic puzzle with 5 houses.
        Clue 1: Peter is in house 1
        Clue 2: Alice is in house 2
        Clue 3: The person in house 1 has a bird
        """,
        response="""
        Reasoning:
        1. Peter is in house 1 (from clue 1)
        2. Alice is in house 2 (from clue 2)
        3. Peter is in house 2 (CONTRADICTION!)
        
        <answer>
        {"header": ["House", "Name"], "rows": [["1", "Peter"], ["2", "Alice"]]}
        </answer>
        """,
        correct_answer=json.dumps({
            "header": ["House", "Name"],
            "rows": [["1", "Peter"], ["2", "Alice"]]
        })
    )
    
    # 初始化检测器（需要LLM配置）
    # 在实际使用中，从配置文件加载LLM
    # llm = SimplifiedAsyncOpenAI(...)
    # detector = LogicConflictDetector(llm=llm)
    
    # 这里演示不使用LLM的情况
    detector = LogicConflictDetector(llm=None)
    
    # 检测冲突
    conflict_analysis = detector.detect_conflicts(sample)
    
    print(f"\n冲突检测结果:")
    print(f"  是否有冲突: {conflict_analysis['has_conflicts']}")
    print(f"  冲突总数: {conflict_analysis['total_conflicts']}")
    
    # 如果有LLM，生成经验
    if detector.llm:
        experience = await detector.generate_experience(
            conflict_analysis,
            sample.raw_question or "",
            sample.response or ""
        )
        if experience:
            print(f"\n生成的经验总结:")
            print(f"  {experience}")
    else:
        print("\n(未配置LLM，跳过经验生成)")


async def example_batch_analysis():
    """示例3: 批量分析多个样本"""
    print("\n" + "=" * 70)
    print("示例3: 批量分析多个样本")
    print("=" * 70)
    
    # 创建多个样本
    samples = [
        EvaluationSample(
            dataset="ZebraLogic-Test",
            raw_question="Logic puzzle 1",
            response="1. Peter is in house 1\n2. Peter is in house 2",
            correct_answer="{}"
        ),
        EvaluationSample(
            dataset="ZebraLogic-Test",
            raw_question="Logic puzzle 2",
            response="1. Alice has bird\n2. Alice has cat",
            correct_answer="{}"
        ),
    ]
    
    detector = LogicConflictDetector(llm=None)
    
    print(f"\n分析 {len(samples)} 个样本:")
    for i, sample in enumerate(samples, 1):
        conflict_analysis = detector.detect_conflicts(sample)
        print(f"\n样本 {i}:")
        print(f"  冲突数: {conflict_analysis['total_conflicts']}")
        print(f"  摘要: {conflict_analysis['summary']}")


async def main():
    """运行所有示例"""
    await example_single_sample()
    await example_with_experience_generation()
    await example_batch_analysis()
    
    print("\n" + "=" * 70)
    print("所有示例完成！")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

